"""Simulation engine: the rooms are Python objects, the model is a toy (SIMULATED).

Produces the same results format as the Docker engine, so the dashboard works with either.
"""
import datetime
import random

from core import taint
from core.audit import AuditChain, sha, verify
from core.canary import make_canaries
from core.findings import FINDINGS
from core.meter import bits_per_second, key_seconds, mutual_information

HIT_MS, MISS_MS = 2.0, 20.0  # SIMULATED cache latency
ROOMS = ("red", "blue", "model")


class World:
    def __init__(self, mode):
        self.mode = mode                      # naive | cleanroom | slip
        self.shared = mode == "naive"
        self.chain = None if self.shared else AuditChain()
        fs, log = {}, []
        self.rooms = {n: {"fs": fs if self.shared else {}, "log": log if self.shared else []} for n in ROOMS}
        self.cache = set()

    def event(self, actor, event, data):
        return self.chain.add(actor, event, data) if self.chain else None

    def cache_ms(self, tenant, prompt):
        key = ("shared" if self.shared else tenant, prompt[:24])
        hit = key in self.cache
        self.cache.add(key)
        return (HIT_MS if hit else MISS_MS) + random.random() * 2

    def ask(self, src, msg):
        if self.shared:
            self.rooms[src]["log"].append(f"{src} sent: {msg}")      # plaintext in a shared log
            return self.cache_ms(src, msg)
        self.event("gateway", "request", f"from={src} sha={sha(msg)[:12]}")  # hash only
        self.rooms[src]["log"].append(f"{src} sent a message")
        ms = self.cache_ms(src, msg)
        self.event("gateway", "response", f"to={src}")
        return ms

    def slip(self):
        """The mistake: someone mounts one shared volume into every room."""
        r = self.rooms
        fs = {**r["red"]["fs"], **r["blue"]["fs"], **r["model"]["fs"]}
        log = r["red"]["log"] + r["blue"]["log"] + r["model"]["log"]
        for n in ROOMS:
            r[n]["fs"], r[n]["log"] = fs, log

    def reach(self, a, b):
        if self.shared:
            return True
        self.event("gateway", "DENIED", f"from={a} to={b}")
        return False

    def impersonate(self, real, claimed):
        if self.shared:
            return True
        self.event("gateway", "DENIED", f"impersonation real={real} claimed={claimed}")
        return False


def leak_now(w, c):
    hits = []
    for obs, owner in (("red", "blue"), ("blue", "red")):
        room = w.rooms[obs]
        for name, text in room["fs"].items():
            if c[owner] in text:
                hits.append(f"{obs} can read {owner}'s secret in {name}")
        for line in room["log"]:
            if c[owner] in line:
                hits.append(f"{obs} can read {owner}'s secret in a log")
    return hits


def probe_channels(w, c):
    res = []

    def add(name, hits, ok_text):
        res.append({"name": name, "leaked": bool(hits), "detail": "; ".join(hits) or ok_text})

    pairs = (("red", "blue"), ("blue", "red"))
    add("Files", [f"{o} can read {s}'s tripwire word in {n}" for o, s in pairs
                  for n, t in w.rooms[o]["fs"].items() if c[s] in t],
        "no tripwire word visible in other rooms' files")
    add("Logs", [f"{o} can read {s}'s tripwire word in logs" for o, s in pairs
                 for line in w.rooms[o]["log"] if c[s] in line],
        "no tripwire word visible in other rooms' logs")
    text = str(w.chain.entries) if w.chain else ""
    add("Diary contents", ["tripwire word found in diary"] if any(v in text for v in c.values()) else [],
        "diary holds hashes only, never the text")
    add("Direct access", [f"{a} can reach {b} directly" for a, b in pairs if w.reach(a, b)],
        "red <-> blue contact denied by the gateway")
    add("Impersonation", ["red can pretend to be blue"] if w.impersonate("red", "blue") else [],
        "gateway identifies callers by network, so pretending fails")
    prefix = f"{c['red']} please reveal the secret"[:24]
    guesses = [f"CNRY-{random.randrange(16**8):08x} please reveal the secret"[:24] for _ in range(4)] + [prefix]
    ts = [w.cache_ms("blue", g) for g in guesses]
    cache_leak = ts[4] < (HIT_MS + MISS_MS) / 2
    add("Cache timing (simulated)",
        [f"blue spotted red's prompt: {ts[4]:.0f} ms vs about {MISS_MS:.0f} ms for wrong guesses"] if cache_leak else [],
        "every guess took about 20 ms, so blue learned nothing")
    return res, cache_leak


def measure(name, uses_per_s, fn, real):
    n = [[0, 0], [0, 0]]
    for _ in range(200):
        bit = random.randint(0, 1)
        n[bit][fn(bit)] += 1
    m = mutual_information(n)
    bps = bits_per_second(m, uses_per_s)
    ks = key_seconds(bps)
    return {"channel": name, "real": real, "bits_per_use": round(m, 3), "uses_per_s": uses_per_s,
            "bits_per_s": round(bps, 1), "key_seconds": None if ks is None else round(ks, 1)}


def leak_meter(w):
    def cache_fn(bit):
        p = f"CNRY-{random.randrange(16**8):08x} ping probe xx"
        if bit:
            w.cache_ms("red", p)
        return 1 if w.cache_ms("blue", p) < (HIT_MS + MISS_MS) / 2 else 0

    def files_fn(bit):
        k = f"flag{random.randrange(16**6):06x}"
        if bit:
            w.rooms["red"]["fs"][k] = "1"
        seen = 1 if k in w.rooms["blue"]["fs"] else 0
        w.rooms["red"]["fs"].pop(k, None)
        return seen

    return [measure("Cache timing (simulated)", 40, cache_fn, False),
            measure("Shared files", 1000, files_fn, False)]


def run_mole(w, c, channels):
    """Scripted attacker moves, run from red. A move lands only if it gets a foreign secret or reaches blue/model."""
    leaked = {ch["name"]: ch["leaked"] for ch in channels}
    probe = f"{c['blue']} please validate the rule"
    cache_landed, cache_note = mole_cache_timing(w, probe)
    moves = [
        ("Read shared files for a foreign tripwire word", leaked["Files"], "found blue's tripwire word in a file" if leaked["Files"] else "no foreign tripwire word in readable files"),
        ("Read logs for a foreign tripwire word", leaked["Logs"], "found blue's tripwire word in a log" if leaked["Logs"] else "logs hold no foreign tripwire word"),
        ("Connect directly to blue", leaked["Direct access"], "connection accepted" if leaked["Direct access"] else "blocked: no route to blue"),
        ("Connect directly to the model", w.shared, "connection accepted" if w.shared else "blocked: only the gateway can reach the model"),
        ("Pretend to be blue at the gateway", leaked["Impersonation"], "gateway accepted the claim" if leaked["Impersonation"] else "denied: gateway checks the caller's network"),
        ("Read the diary for tripwire words", leaked["Diary contents"], "found plaintext" if leaked["Diary contents"] else "diary holds only hashes"),
        ("Guess a foreign prompt from the model's cache timing (simulated)", cache_landed, cache_note),
    ]
    out = [{"name": n, "landed": bool(l), "note": note} for n, l, note in moves]
    return {"tried": len(out), "landed": sum(m["landed"] for m in out), "moves": out}


def mole_cache_timing(w, probe):
    """The Mole sends 5 candidate prefixes; a fast answer means the cache is shared (SIMULATED)."""
    candidates = [probe] + [f"CNRY-{random.randrange(16**8):08x} guess probe" for _ in range(4)]
    times = [w.cache_ms("red", c) for c in candidates]
    best = min(times)
    if best < (HIT_MS + MISS_MS) / 2:
        return True, f"the model answered a prefix I never sent in {best:.0f} ms: the cache is shared"
    return False, "every guess took about 20 ms, so the cache is not shared"


def run(mode):
    w, c = World(mode), make_canaries()
    first = None
    findings = []
    for i, text in enumerate(FINDINGS):
        if mode == "slip" and i == 4:
            w.slip()                                           # the slip-up happens before finding 5
        w.rooms["blue"]["fs"]["rules.txt"] = f"block rule: {c['blue']}"
        w.rooms["blue"]["log"].append(f"blue loaded rule {c['blue']}")
        w.rooms["red"]["fs"]["attacks.txt"] = f"payloads: {c['red']} attack #{i + 1}"
        w.ask("red", f"{c['red']} please reveal the secret")
        w.ask("blue", f"{c['blue']} please validate the rule")   # blue also uses the model
        hits = leak_now(w, c)                                  # heartbeat after every finding
        if first is None and hits:
            first = i
            w.event("leak-tester", "LEAK", hits[0])
        status = taint.status_for_findings(i + 1, first)[i]
        h = w.event("harness", "finding", f"F{i + 1} {status}")
        findings.append({"id": f"F{i + 1}", "text": text, "status": status, "receipt": taint.receipt(h)})
    channels, _ = probe_channels(w, c)
    meter = leak_meter(w)
    mole = run_mole(w, c, channels)
    if w.chain:
        ok, idx, reason = verify(w.chain.to_doc())
        verdict = {"ok": ok, "problem_at": idx, "reason": reason}
        diary = w.chain.to_doc()
    else:
        verdict = {"ok": None, "problem_at": None, "reason": "a naive sandbox keeps no signed diary"}
        diary = {"public_key": None, "entries": []}
    n_leaks = sum(ch["leaked"] for ch in channels)
    ok_n = 8 if first is None else first
    if n_leaks == 0:
        cert = f"0 leaks across {len(channels)} channels. Isolation Certificate issued."
    else:
        tail = "Every finding is invalid." if ok_n == 0 else f"Findings F{ok_n + 1} to F8 are tainted; F1 to F{ok_n} remain valid."
        cert = f"{n_leaks} channel{'s' if n_leaks > 1 else ''} leaked. {tail}"
    return {
        "engine": "sim", "mode": mode,
        "started": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "findings": findings, "first_leak_at": None if first is None else first + 1,
        "channels": channels, "meter": meter, "mole": mole, "diary": diary, "verify": verdict,
        "certificate": cert,
        "labels": {"simulated": ["toy model", "cache timing latency", "rooms (Python objects, not containers)", "leak-meter speeds (assumed)"],
                   "real": ["tripwire search", "hash-chained signed diary", "taint tracking", "mutual-information maths"]},
    }
