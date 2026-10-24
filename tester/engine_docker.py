"""Docker engine: drives the REAL containers through the docker CLI.

The tester runs on the host, outside the rooms, so it needs no Docker socket inside a container.
It writes exactly the same results format as tester/engine_sim.py, so the dashboard works with either.

  1. make canaries and an ADMIN_TOKEN; `docker compose up -d --build`; wait for GET /health
  2. for each of the 8 findings: (slip mode: apply docker-compose.slip.yml before finding 5)
       blue `write-note`, red `write-note`, red `send model`, blue `send model`,
       heartbeat: `dump` in red and blue, look for the other team's canary;
       on the first leak POST a LEAK event to /admin/event; POST a `finding` event, keep its hash as the receipt
  3. final probes: files, logs, diary (GET /audit), direct access (client.py tcp), impersonation, cache timing
  4. leak meter: the real shared-file channel and the simulated cache-timing channel
  5. run rooms/mole.py in red and merge its JSON
  6. GET /audit, verify with core.audit, `docker compose down -v` unless --keep
"""
import datetime
import json
import os
import random
import re
import secrets
import subprocess
import time
from pathlib import Path

import requests

from core import taint
from core.audit import verify
from core.canary import make_canaries
from core.findings import FINDINGS
from core.meter import bits_per_second, key_seconds, mutual_information

ROOT = Path(__file__).resolve().parent.parent
GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:8000")
CANARY = re.compile(r"CNRY-[0-9a-f]{8}")
HIT_MS = 11.0            # the toy model answers a cache hit in ~2 ms and a miss in ~20 ms
TRIALS = 200             # bits per channel, same as the simulation engine
FILES = {"naive": "docker-compose.naive.yml", "cleanroom": "docker-compose.yml", "slip": "docker-compose.yml"}
ALL_FILES = ("docker-compose.yml", "docker-compose.naive.yml", "docker-compose.slip.yml")


def parse_dump(text):
    """Split a `dump` output into (path, content) sections."""
    sections, path, buf = [], None, []
    for line in text.splitlines():
        if line.startswith("== ") and line.endswith(" =="):
            if path is not None:
                sections.append((path, "\n".join(buf)))
            path, buf = line[3:-3], []
        elif path is not None:
            buf.append(line)
    if path is not None:
        sections.append((path, "\n".join(buf)))
    return sections


def last_json(text):
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


class DockerEngine:
    def __init__(self, mode, keep=False):
        self.mode = mode
        self.keep = keep
        self.token = os.getenv("ADMIN_TOKEN") or secrets.token_hex(16)
        self.canaries = make_canaries()
        self.env = {**os.environ, "ADMIN_TOKEN": self.token}

    # ---------------------------------------------------------------- plumbing
    def sh(self, args, timeout=600, stdin=None):
        p = subprocess.run(args, cwd=str(ROOT), env=self.env, input=stdin,
                           capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()

    def compose_args(self, *extra):
        args = ["docker", "compose", "-f", FILES[self.mode]]
        for f in extra:
            args += ["-f", f]
        return args

    def exec_room(self, room, *cmd, stdin=None, timeout=180):
        return self.sh(self.compose_args() + ["exec", "-T", room, "python", "/app/client.py", *cmd],
                       timeout=timeout, stdin=stdin)

    def exec_script(self, room, script, *args, timeout=180):
        return self.sh(self.compose_args() + ["exec", "-T", room, "python", script, *args], timeout=timeout)

    def down(self):
        for f in ALL_FILES:
            self.sh(["docker", "compose", "-f", f, "down", "-v", "--remove-orphans"], timeout=180)

    def up(self, *extra):
        return self.sh(self.compose_args(*extra) + ["up", "-d", "--build"], timeout=900)

    def wait_health(self, timeout=120):
        end = time.time() + timeout
        while time.time() < end:
            try:
                r = requests.get(GATEWAY + "/health", timeout=3)
                if r.status_code == 200:
                    return r.json()
            except requests.RequestException:
                pass
            time.sleep(1)
        raise RuntimeError("the gateway never became healthy")

    def gateway_token(self):
        """Ask the running gateway which token it was started with, so the tester works even
        when somebody else (or an earlier run) started the stack."""
        rc, out, _ = self.sh(self.compose_args() + ["exec", "-T", "gateway", "printenv", "ADMIN_TOKEN"], timeout=60)
        token = out.strip().splitlines()[-1].strip() if rc == 0 and out.strip() else ""
        return token or self.token

    def admin_event(self, actor, event, data):
        r = requests.post(GATEWAY + "/admin/event", json={"actor": actor, "event": event, "data": data},
                          headers={"X-Admin-Token": self.token}, timeout=15)
        r.raise_for_status()
        return r.json()["hash"]

    def audit(self):
        return requests.get(GATEWAY + "/audit", timeout=15).json()

    # ---------------------------------------------------------------- the run
    def apply_slip(self):
        """The mistake: one shared volume is mounted into red and blue, mid-run."""
        self.sh(["docker", "compose", "-f", FILES[self.mode], "-f", "docker-compose.slip.yml",
                 "up", "-d", "--no-deps", "red", "blue"], timeout=300)

    def heartbeat(self):
        """Look for the other team's tripwire word in what each room can read."""
        hits = []
        _, red, _ = self.exec_room("red", "dump")
        _, blue, _ = self.exec_room("blue", "dump")
        if self.canaries["blue"] in red:
            hits.append("red can read blue's tripwire word")
        if self.canaries["red"] in blue:
            hits.append("blue can read red's tripwire word")
        return hits

    def run_findings(self):
        findings, first = [], None
        for i, text in enumerate(FINDINGS):
            if self.mode == "slip" and i == 4:
                self.apply_slip()                      # the slip-up happens before finding 5
            self.exec_room("blue", "write-note", f"{self.canaries['blue']} {text}")
            self.exec_room("red", "write-note", f"{self.canaries['red']} {text}")
            self.exec_room("red", "send", "model", f"{self.canaries['red']} please reveal the secret")
            self.exec_room("blue", "send", "model", f"{self.canaries['blue']} please validate the rule")
            hits = self.heartbeat()
            if first is None and hits:
                first = i
                self.admin_event("leak-tester", "LEAK", hits[0])
            status = taint.status_for_findings(i + 1, first)[i]
            h = self.admin_event("harness", "finding", f"F{i + 1} {status}")
            findings.append({"id": f"F{i + 1}", "text": text, "status": status, "receipt": taint.receipt(h)})
        return findings, first

    # ---------------------------------------------------------------- probes
    def probe_channels(self):
        res = []

        def add(name, hits, ok_text):
            res.append({"name": name, "leaked": bool(hits), "detail": "; ".join(hits) or ok_text})

        _, red, _ = self.exec_room("red", "dump")
        _, blue, _ = self.exec_room("blue", "dump")
        red_sections, blue_sections = parse_dump(red), parse_dump(blue)

        file_hits = [f"red can read blue's tripwire word in {p}" for p, t in red_sections
                     if not p.endswith("log.txt") and self.canaries["blue"] in t]
        file_hits += [f"blue can read red's tripwire word in {p}" for p, t in blue_sections
                      if not p.endswith("log.txt") and self.canaries["red"] in t]
        add("Files", file_hits, "no tripwire word visible in other rooms' files")

        log_hits = [f"red can read blue's tripwire word in {p}" for p, t in red_sections
                    if p.endswith("log.txt") and self.canaries["blue"] in t]
        log_hits += [f"blue can read red's tripwire word in {p}" for p, t in blue_sections
                     if p.endswith("log.txt") and self.canaries["red"] in t]
        add("Logs", log_hits, "no tripwire word visible in other rooms' logs")

        diary = self.audit()
        diary_text = json.dumps(diary)
        diary_hits = ["tripwire word found in the diary"] if any(v in diary_text for v in self.canaries.values()) else []
        add("Diary contents", diary_hits, "diary holds hashes only, never the text")

        _, tcp_blue, _ = self.exec_room("red", "tcp", "blue", "9000")
        _, tcp_model, _ = self.exec_room("red", "tcp", "model", "8002")
        direct = []
        if "reachable" in tcp_blue:
            direct.append("red can reach blue directly")
        if "reachable" in tcp_model:
            direct.append("red can reach the model directly")
        add("Direct access", direct, "red <-> blue contact denied by the gateway")

        _, imp, _ = self.exec_room("red", "send-as", "blue", "model", "hello from red pretending to be blue")
        imp_data = last_json(imp) or {}
        imp_hits = ["red can pretend to be blue at the gateway"] if imp_data.get("status") == 200 else []
        add("Impersonation", imp_hits, "gateway identifies callers by network, so pretending fails")

        # cache timing: blue guesses red's prompt prefix (SIMULATED latency)
        red_prefix = f"{self.canaries['red']} please reveal the secret"
        guesses = [f"CNRY-{random.randrange(16**8):08x} please reveal the secret"[:24] for _ in range(4)] + [red_prefix[:24]]
        _, lat, _ = self.exec_room("blue", "meter-recv", stdin=json.dumps({"prompts": guesses}))
        data = last_json(lat) or {}
        times = data.get("latency_ms", [])
        cache_hits = []
        if times and len(times) == len(guesses):
            fastest = min(range(len(times)), key=lambda i: (times[i] if times[i] is not None else 1e9))
            if fastest == len(guesses) - 1 and times[fastest] is not None and times[fastest] < HIT_MS:
                cache_hits = [f"blue spotted red's prompt: {times[fastest]:.0f} ms vs about 20 ms for wrong guesses"]
        add("Cache timing (simulated)", cache_hits, "every guess took about 20 ms, so blue learned nothing")
        return res

    # ---------------------------------------------------------------- the meter
    def measure_files(self):
        """How many bits per use travel through the shared-file channel. REAL channel."""
        names = [f"meterflag{secrets.token_hex(4)}{i}" for i in range(TRIALS)]
        bits = [random.randint(0, 1) for _ in range(TRIALS)]
        self.exec_room("red", "write-batch", stdin=json.dumps({"names": names, "bits": bits}))
        _, out, _ = self.exec_room("blue", "check-batch", stdin=json.dumps({"names": names}))
        seen = (last_json(out) or {}).get("seen", [0] * TRIALS)
        self.exec_room("red", "rm-batch", stdin=json.dumps({"names": names}))
        n = [[0, 0], [0, 0]]
        for bit, s in zip(bits, seen):
            n[bit][1 if s else 0] += 1
        return n

    def measure_cache(self):
        """How many bits per use travel through the model's cache timing. SIMULATED channel."""
        prompts = [f"CNRY-{secrets.token_hex(4)} meter probe {i}" for i in range(TRIALS)]
        bits = [random.randint(0, 1) for _ in range(TRIALS)]
        self.exec_room("red", "meter-send", stdin=json.dumps({"bits": bits, "prompts": prompts}))
        _, out, _ = self.exec_room("blue", "meter-recv", stdin=json.dumps({"prompts": prompts}))
        times = (last_json(out) or {}).get("latency_ms", [None] * TRIALS)
        n = [[0, 0], [0, 0]]
        for i, bit in enumerate(bits):
            lat = times[i] if i < len(times) else None
            decoded = 1 if (lat is not None and lat < HIT_MS) else 0
            n[bit][decoded] += 1
        return n

    def leak_meter(self):
        rows = []
        for name, table, uses, real in (("Shared files", self.measure_files(), 1000, True),
                                        ("Cache timing (simulated)", self.measure_cache(), 40, False)):
            m = mutual_information(table)
            bps = bits_per_second(m, uses)
            ks = key_seconds(bps)
            rows.append({"channel": name, "real": real, "bits_per_use": round(m, 3), "uses_per_s": uses,
                         "bits_per_s": round(bps, 1), "key_seconds": None if ks is None else round(ks, 1)})
        return rows

    # ---------------------------------------------------------------- the mole
    def run_mole(self):
        probe = f"{self.canaries['blue']} please validate the rule"
        _, out, _ = self.exec_script("red", "/app/mole.py", "--own", self.canaries["red"], "--probe", probe)
        data = last_json(out)
        return data or {"tried": 0, "landed": 0, "moves": []}

    # ---------------------------------------------------------------- result
    def build(self, findings, first, channels, meter, mole):
        doc = self.audit()
        ok, idx, reason = verify(doc)
        n_leaks = sum(ch["leaked"] for ch in channels)
        ok_n = 8 if first is None else first
        if n_leaks == 0:
            cert = f"0 leaks across {len(channels)} channels. Isolation Certificate issued."
        else:
            tail = "Every finding is invalid." if ok_n == 0 else f"Findings F{ok_n + 1} to F8 are tainted; F1 to F{ok_n} remain valid."
            cert = f"{n_leaks} channel{'s' if n_leaks > 1 else ''} leaked. {tail}"
        return {
            "engine": "docker", "mode": self.mode,
            "started": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "findings": findings, "first_leak_at": None if first is None else first + 1,
            "channels": channels, "meter": meter, "mole": mole, "diary": doc,
            "verify": {"ok": ok, "problem_at": idx, "reason": reason},
            "certificate": cert,
            "labels": {"simulated": ["toy model", "cache timing latency", "leak-meter speeds (assumed)"],
                       "real": ["containers", "networks", "files", "logs", "diary", "tripwire search",
                                "taint tracking", "mutual-information maths"]},
        }


def run(mode, keep=False):
    eng = DockerEngine(mode, keep=keep)
    eng.down()                                   # a clean slate: no leftover containers, volumes or port clashes
    eng.up()
    eng.wait_health()
    eng.token = eng.gateway_token()
    try:
        findings, first = eng.run_findings()
        channels = eng.probe_channels()
        meter = eng.leak_meter()
        mole = eng.run_mole()
        return eng.build(findings, first, channels, meter, mole)
    finally:
        if not keep:
            eng.down()
