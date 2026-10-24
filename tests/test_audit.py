from core.audit import AuditChain, verify, entry_hash


def make():
    c = AuditChain()
    for i in range(4):
        c.add("gateway", "request", f"from=red sha=abc{i}")
    return c.to_doc()


def test_valid_chain():
    assert verify(make())[0] is True


def test_tamper_data_detected():
    d = make()
    d["entries"][1]["data"] += "x"
    ok, i, _ = verify(d)
    assert ok is False and i == 1


def test_forged_hash_fails_signature():
    d = make()
    e = d["entries"][1]
    e["data"] = "forged"
    e["hash"] = entry_hash(e["i"], e["t"], e["actor"], e["event"], e["data"], e["prev"])
    d["entries"][2]["prev"] = e["hash"]
    ok, _, _ = verify(d)
    assert ok is False
