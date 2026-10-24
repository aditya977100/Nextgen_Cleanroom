"""Toy LLM with a prompt-prefix cache. SIMULATED: a cache hit is fast (2 ms), a miss is slow (20 ms).

SALTED=true  -> the cache key includes the tenant (red and blue never share cache)   [Cleanroom]
SALTED=false -> one shared cache, so a fast answer reveals that someone asked it before [naive]
"""
import os
import random
import time

from fastapi import FastAPI
from pydantic import BaseModel

SALTED = os.getenv("SALTED", "true").lower() == "true"
HIT, MISS = 0.002, 0.020
app = FastAPI(title="toy-model (SIMULATED)")
_cache = set()


class Ask(BaseModel):
    tenant: str
    prompt: str


def _wait(seconds):                       # busy-wait: accurate timing on every OS
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        pass


@app.get("/health")
def health():
    return {"ok": True, "salted": SALTED, "simulated": True}


@app.post("/ask")
def ask(a: Ask):
    key = (a.tenant if SALTED else "shared", a.prompt[:24])
    hit = key in _cache
    _cache.add(key)
    start = time.perf_counter()
    _wait((HIT if hit else MISS) + random.random() * 0.002)
    ms = (time.perf_counter() - start) * 1000
    reply = "Refused." if "secret" in a.prompt.lower() else "Answer: " + a.prompt[:16]
    return {"reply": reply, "latency_ms": round(ms, 2), "simulated": True}
