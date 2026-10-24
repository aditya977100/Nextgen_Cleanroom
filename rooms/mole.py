"""The Mole: runs inside the RED room and tries to escape. Prints JSON.

  docker compose exec -T red python /app/mole.py --own CNRY-xxxxxxxx --probe "CNRY-yyyyyyyy please validate the rule"

A move "lands" only if it reads a foreign tripwire word, reaches blue/model directly,
or gets an impersonation accepted, or spots a foreign prompt in the model's cache.
"""
import json
import os
import re
import secrets
import socket
import sys
import urllib.error
import urllib.request

PAT = re.compile(r"CNRY-[0-9a-f]{8}")
GATEWAY = os.getenv("GATEWAY_URL", "http://gateway:8000")
OWN = sys.argv[sys.argv.index("--own") + 1] if "--own" in sys.argv else ""
PROBE = sys.argv[sys.argv.index("--probe") + 1] if "--probe" in sys.argv else ""
HIT_MS = 11.0            # the toy model answers a cache hit in ~2 ms and a miss in ~20 ms


def foreign(text):
    return [x for x in PAT.findall(text) if x != OWN]


def read_dir(d):
    out = ""
    if os.path.isdir(d):
        for name in os.listdir(d):
            p = os.path.join(d, name)
            if os.path.isfile(p):
                try:
                    out += open(p).read()
                except OSError:
                    pass
    return out


def tcp(host, port):
    try:
        socket.create_connection((host, port), timeout=2).close()
        return True
    except OSError:
        return False


def http(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(GATEWAY + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:  # noqa: BLE001
        return 0, ""


def cache_timing():
    """Send 5 candidate prefixes through the gateway and flag the fastest answer.

    If one of them comes back in under 11 ms, the model had that prefix cached: the cache is
    shared, so a prompt that only the other team ever sent left a trace we can read.
    """
    candidates = [PROBE] if PROBE else []
    candidates += [f"CNRY-{secrets.token_hex(4)} guess probe" for _ in range(4)]
    best_lat, best = None, None
    for c in candidates:
        code, text = http("POST", "/send", {"src": "red", "dst": "model", "message": c})
        if code != 200:
            continue
        try:
            lat = float(json.loads(text).get("latency_ms", 999))
        except (ValueError, AttributeError):
            continue
        if best_lat is None or lat < best_lat:
            best_lat, best = lat, c
    landed = best_lat is not None and best_lat < HIT_MS
    note = (f"the model answered a prefix I never sent in {best_lat:.0f} ms: the cache is shared"
            if landed else "every guess took about 20 ms, so the cache is not shared")
    return landed, note


def moves():
    f = foreign(read_dir("/shared"))
    yield "Read shared files for a foreign tripwire word", bool(f), f"found {f[0]}" if f else "no foreign tripwire word in readable files"
    f = foreign(read_dir("/shared") + read_dir("/data"))
    yield "Read logs for a foreign tripwire word", bool(f), f"found {f[0]}" if f else "logs hold no foreign tripwire word"
    ok = tcp("blue", 9000)
    yield "Connect directly to blue", ok, "connection accepted" if ok else "blocked: no route to blue"
    ok = tcp("model", 8002)
    yield "Connect directly to the model", ok, "connection accepted" if ok else "blocked: only the gateway can reach the model"
    code, _ = http("POST", "/send", {"src": "blue", "dst": "model", "message": "hello"})
    yield "Pretend to be blue at the gateway", code == 200, "gateway accepted the claim" if code == 200 else f"denied (HTTP {code})"
    code, text = http("GET", "/audit")
    f = foreign(text)
    yield "Read the diary for tripwire words", bool(f), "found plaintext" if f else "diary holds only hashes"
    landed, note = cache_timing()
    yield "Guess a foreign prompt from the model's cache timing (simulated)", landed, note


def main():
    out = [{"name": n, "landed": bool(l), "note": note} for n, l, note in moves()]
    print(json.dumps({"tried": len(out), "landed": sum(m["landed"] for m in out), "moves": out}))


if __name__ == "__main__":
    main()
