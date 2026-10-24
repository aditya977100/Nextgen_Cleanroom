"""The sealed diary: every event is hashed, linked to the previous one, and signed (Ed25519).

Hash input is a plain string "i|t|actor|event|data|prev" so a browser can recompute it too.
"""
import hashlib
import json
import sys
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

GENESIS = "0" * 64


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def entry_hash(i, t, actor, event, data, prev):
    return sha(f"{i}|{t}|{actor}|{event}|{data}|{prev}")


class AuditChain:
    def __init__(self):
        self._key = Ed25519PrivateKey.generate()
        raw = self._key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.public_key = raw.hex()
        self.entries = []

    def add(self, actor, event, data):
        """Append one event. `data` must be a plain string. Returns the entry hash."""
        prev = self.entries[-1]["hash"] if self.entries else GENESIS
        i, t = len(self.entries), int(time.time() * 1000)
        h = entry_hash(i, t, actor, event, data, prev)
        self.entries.append({"i": i, "t": t, "actor": actor, "event": event, "data": str(data),
                             "prev": prev, "hash": h, "sig": self._key.sign(h.encode()).hex()})
        return h

    def to_doc(self):
        return {"public_key": self.public_key, "entries": self.entries}

    def save(self, path):
        with open(path, "w") as f:
            json.dump(self.to_doc(), f, indent=1)


def verify(doc):
    """Check hashes, links and signatures. Returns (ok, index_of_first_problem, reason)."""
    pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(doc["public_key"]))
    prev = GENESIS
    for e in doc["entries"]:
        h = entry_hash(e["i"], e["t"], e["actor"], e["event"], e["data"], e["prev"])
        if e["prev"] != prev or h != e["hash"]:
            return False, e["i"], "hash chain broken (an entry was changed)"
        try:
            pub.verify(bytes.fromhex(e["sig"]), h.encode())
        except Exception:
            return False, e["i"], "signature invalid"
        prev = e["hash"]
    return True, None, "all entries valid"


if __name__ == "__main__":
    # python -m core.audit results/sim-cleanroom.json
    doc = json.load(open(sys.argv[-1]))
    doc = doc.get("diary", doc)
    ok, i, why = verify(doc)
    print("VALID" if ok else f"TAMPERED at entry {i}: {why}")
    sys.exit(0 if ok else 1)
