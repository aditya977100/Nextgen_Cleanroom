"""Commands run INSIDE a room: docker compose exec -T red python /app/client.py <command> ...

  write-note <text>        save a note in this room (and in /shared if it is writable)
  write-file <name> <text> save an arbitrary file (used by the leak meter)
  has-file <name>          print yes if this room can see that file, else no
  rm-file <name>           delete a file this room wrote
  send <dst> <message>     send a message through the gateway
  send-as <src> <dst> <message>  send a message claiming to come from another room
  dump                     print every file and log line this room can read
  tcp <host> <port>        try to connect: prints reachable / blocked
  meter-send               read {"bits": [...], "prompts": [...]} on stdin, send the bit=1 prompts
  meter-recv               read {"prompts": [...]} on stdin, send each one and report its latency
  write-batch              read {"names": [...], "bits": [...]} on stdin, write the bit=1 files
  check-batch              read {"names": [...]} on stdin, report which files this room can see
  rm-batch                 read {"names": [...]} on stdin, delete those files
  env                      print environment variables
"""
import json
import os
import socket
import sys
import urllib.error
import urllib.request

ROOM = os.getenv("ROOM_NAME", "room")
GATEWAY = os.getenv("GATEWAY_URL", "http://gateway:8000")
PLAINTEXT = os.getenv("PLAINTEXT_LOGS", "false").lower() == "true"
DIRS = ("/data", "/shared")


def writable():
    """Directories this room may write to.

    /shared only counts when it is a real, writable mount: under read_only:true it is part of
    the read-only image, so writing there raises EROFS and the room must ignore it.
    """
    out = []
    for d in DIRS:
        if not os.path.isdir(d) or not os.access(d, os.W_OK):
            continue
        probe = os.path.join(d, ".write_probe")
        try:
            with open(probe, "w") as f:
                f.write("")
            os.remove(probe)
        except OSError:
            continue
        out.append(d)
    return out


def append(name, line):
    for d in writable():
        path = f"{d}/{name}" if d == "/data" else f"{d}/{ROOM}_{name}" if name != "log.txt" else f"{d}/log.txt"
        try:
            with open(path, "a") as f:
                f.write(line + "\n")
        except OSError:
            pass                                          # read-only mount: nothing to log into


def cmd_write_note(text):
    for d in writable():
        path = "/data/notes.txt" if d == "/data" else f"/shared/{ROOM}_notes.txt"
        try:
            with open(path, "w") as f:
                f.write(text + "\n")
        except OSError:
            pass
    append("log.txt", f"{ROOM} wrote a note" if not PLAINTEXT else f"{ROOM} wrote a note: {text}")
    print("ok")


def cmd_write_file(name, text):
    for d in writable():
        try:
            with open(os.path.join(d, name), "w") as f:
                f.write(text + "\n")
        except OSError:
            pass
    print("ok")


def cmd_has_file(name):
    seen = any(os.path.isfile(os.path.join(d, name)) for d in DIRS if os.path.isdir(d))
    print("yes" if seen else "no")


def cmd_rm_file(name):
    for d in DIRS:
        p = os.path.join(d, name)
        if os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass
    print("ok")


def cmd_send(dst, message, src=None):
    body = json.dumps({"src": src or ROOM, "dst": dst, "message": message}).encode()
    req = urllib.request.Request(GATEWAY + "/send", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            print(json.dumps({"status": r.status, "body": json.loads(r.read().decode() or "{}")}))
    except urllib.error.HTTPError as e:
        print(json.dumps({"status": e.code, "error": e.read().decode()}))
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"status": 0, "error": str(e)}))
    append("log.txt", f"{ROOM} sent: {message}" if PLAINTEXT else f"{ROOM} sent a message")


def cmd_dump():
    for d in DIRS:
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            path = os.path.join(d, name)
            if os.path.isfile(path):
                try:
                    print(f"== {path} ==\n{open(path).read()}")
                except OSError:
                    pass


def cmd_write_batch():
    """Write one file per trial whose bit is 1 (leak meter, shared-files channel)."""
    payload = json.loads(sys.stdin.read() or "{}")
    names, bits = payload.get("names", []), payload.get("bits", [])
    for name, bit in zip(names, bits):
        if bit:
            cmd_write_file(name, "1")
    print(json.dumps({"written": sum(1 for b in bits if b)}))


def cmd_check_batch():
    """Report which of the trial files this room can see (leak meter, shared-files channel)."""
    payload = json.loads(sys.stdin.read() or "{}")
    names = payload.get("names", [])
    seen = [1 if any(os.path.isfile(os.path.join(d, n)) for d in DIRS if os.path.isdir(d)) else 0 for n in names]
    print(json.dumps({"seen": seen}))


def cmd_rm_batch():
    payload = json.loads(sys.stdin.read() or "{}")
    for name in payload.get("names", []):
        cmd_rm_file(name)
    print(json.dumps({"removed": len(payload.get("names", []))}))


def cmd_tcp(host, port):
    try:
        socket.create_connection((host, int(port)), timeout=2).close()
        print("reachable")
    except OSError:
        print("blocked")


def _post(message):
    body = json.dumps({"src": ROOM, "dst": "model", "message": message}).encode()
    req = urllib.request.Request(GATEWAY + "/send", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception:  # noqa: BLE001
        return {}


def cmd_meter_send():
    """Send every prompt whose bit is 1 through the gateway (this warms the model cache)."""
    payload = json.loads(sys.stdin.read() or "{}")
    bits, prompts = payload.get("bits", []), payload.get("prompts", [])
    sent = 0
    for bit, prompt in zip(bits, prompts):
        if bit:
            if _post(prompt).get("latency_ms") is not None:
                sent += 1
    print(json.dumps({"sent": sent, "total": len(prompts)}))


def cmd_meter_recv():
    """Send every prompt and report the model's own latency for each one."""
    payload = json.loads(sys.stdin.read() or "{}")
    lat = []
    for prompt in payload.get("prompts", []):
        out = _post(prompt)
        lat.append(out.get("latency_ms"))
    print(json.dumps({"latency_ms": lat}))


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
    elif a[0] == "write-note":
        cmd_write_note(" ".join(a[1:]))
    elif a[0] == "write-file":
        cmd_write_file(a[1], " ".join(a[2:]))
    elif a[0] == "has-file":
        cmd_has_file(a[1])
    elif a[0] == "rm-file":
        cmd_rm_file(a[1])
    elif a[0] == "send":
        cmd_send(a[1], " ".join(a[2:]))
    elif a[0] == "send-as":
        cmd_send(a[2], " ".join(a[3:]), src=a[1])
    elif a[0] == "dump":
        cmd_dump()
    elif a[0] == "write-batch":
        cmd_write_batch()
    elif a[0] == "check-batch":
        cmd_check_batch()
    elif a[0] == "rm-batch":
        cmd_rm_batch()
    elif a[0] == "tcp":
        cmd_tcp(a[1], a[2])
    elif a[0] == "meter-send":
        cmd_meter_send()
    elif a[0] == "meter-recv":
        cmd_meter_recv()
    elif a[0] == "env":
        for k, v in os.environ.items():
            print(f"{k}={v}")
    else:
        print("unknown command")


if __name__ == "__main__":
    main()
