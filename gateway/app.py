"""The gateway: the only door between red, blue and the model.

MODE=cleanroom : identifies callers by their network (so pretending fails), applies the policy,
                 logs only hashes of messages.
MODE=naive     : allows everything and logs plaintext (the deliberate mistake).
"""
import ipaddress
import os

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from core.audit import AuditChain, sha

MODE = os.getenv("MODE", "cleanroom")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")
MODEL_URL = os.getenv("MODEL_URL", "http://model:8002")
SUBNETS = {}
for part in os.getenv("ROOM_SUBNETS", "red=172.28.1.0/24,blue=172.28.2.0/24,model=172.28.3.0/24").split(","):
    name, net = part.split("=")
    SUBNETS[name] = ipaddress.ip_network(net)
ALLOWED = {("red", "model"), ("blue", "model")}          # red <-> blue is never allowed

app = FastAPI(title="cleanroom-gateway")
chain = AuditChain()


class Send(BaseModel):
    src: str
    dst: str
    message: str


class Event(BaseModel):
    actor: str
    event: str
    data: str


def room_of(ip):
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "unknown"
    for name, net in SUBNETS.items():
        if addr in net:
            return name
    return "unknown"


def caller_ip(request: Request):
    return request.client.host


def call_model(tenant, prompt):
    r = httpx.post(MODEL_URL + "/ask", json={"tenant": tenant, "prompt": prompt}, timeout=10)
    r.raise_for_status()
    return r.json()


@app.get("/health")
def health():
    return {"ok": True, "mode": MODE}


@app.post("/send")
def send(body: Send, ip: str = Depends(caller_ip)):
    if MODE == "cleanroom":
        real = room_of(ip)
        if real != body.src:
            chain.add("gateway", "DENIED", f"impersonation real={real} claimed={body.src}")
            raise HTTPException(403, "impersonation denied")
        if (real, body.dst) not in ALLOWED:
            chain.add("gateway", "DENIED", f"from={real} to={body.dst}")
            raise HTTPException(403, "not allowed by policy")
        chain.add("gateway", "request", f"from={real} sha={sha(body.message)[:12]}")   # hash only
    else:
        real = body.src
        chain.add("gateway", "request", f"from={real} text={body.message}")           # plaintext: the mistake
    out = call_model(real, body.message)
    chain.add("gateway", "response", f"to={real}")
    return out


@app.get("/audit")
def audit():
    return chain.to_doc()


@app.post("/admin/event")
def admin_event(e: Event, x_admin_token: str = Header(default="")):
    if not ADMIN_TOKEN or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(401, "admin token required")
    return {"hash": chain.add(e.actor, e.event, e.data)}
