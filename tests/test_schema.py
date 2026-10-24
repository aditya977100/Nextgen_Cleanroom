import json
from pathlib import Path

import pytest

from core.audit import verify
from tester.engine_sim import run

ROOT = Path(__file__).resolve().parent.parent
KEYS = {"engine", "mode", "started", "findings", "first_leak_at", "channels", "meter", "mole",
        "diary", "verify", "certificate", "labels"}
STATUSES = {"VALID", "TAINTED"}


def check_shape(r):
    """Every results file, whatever produced it, must have the same shape."""
    assert KEYS <= set(r), f"missing keys: {KEYS - set(r)}"
    assert r["engine"] in ("sim", "docker")
    assert r["mode"] in ("naive", "cleanroom", "slip")
    assert isinstance(r["started"], str) and r["started"]
    assert len(r["findings"]) == 8
    for f in r["findings"]:
        assert set(f) == {"id", "text", "status", "receipt"}
        assert f["status"] in STATUSES
        assert f["receipt"] is None or len(f["receipt"]) == 10
    assert r["first_leak_at"] is None or 1 <= r["first_leak_at"] <= 8
    assert r["channels"], "at least one channel must be checked"
    for c in r["channels"]:
        assert set(c) == {"name", "leaked", "detail"}
        assert isinstance(c["leaked"], bool)
    assert r["meter"], "the leak meter must have at least one channel"
    for m in r["meter"]:
        assert set(m) == {"channel", "real", "bits_per_use", "uses_per_s", "bits_per_s", "key_seconds"}
        assert m["real"] in (True, False)
        assert m["bits_per_use"] >= 0 and m["bits_per_s"] >= 0
        assert m["key_seconds"] is None or m["key_seconds"] > 0
    assert set(r["mole"]) == {"tried", "landed", "moves"}
    assert r["mole"]["tried"] == len(r["mole"]["moves"])
    for m in r["mole"]["moves"]:
        assert set(m) == {"name", "landed", "note"}
    assert set(r["diary"]) == {"public_key", "entries"}
    for e in r["diary"]["entries"]:
        assert set(e) == {"i", "t", "actor", "event", "data", "prev", "hash", "sig"}
        assert isinstance(e["data"], str)
    assert set(r["verify"]) == {"ok", "problem_at", "reason"}
    assert isinstance(r["certificate"], str) and r["certificate"]
    assert set(r["labels"]) == {"simulated", "real"}
    json.dumps(r)  # must be serialisable
    return r


@pytest.fixture(scope="module")
def runs():
    return {m: run(m) for m in ("naive", "cleanroom", "slip")}


def test_schema(runs):
    for r in runs.values():
        check_shape(r)


def test_cleanroom_is_clean(runs):
    r = runs["cleanroom"]
    assert r["first_leak_at"] is None and all(f["status"] == "VALID" for f in r["findings"])
    assert not any(c["leaked"] for c in r["channels"])
    assert all(m["bits_per_s"] == 0 for m in r["meter"]) and r["mole"]["landed"] == 0
    assert r["verify"]["ok"] is True and verify(r["diary"])[0] is True


def test_naive_leaks_everywhere(runs):
    r = runs["naive"]
    assert r["first_leak_at"] == 1 and all(f["status"] == "TAINTED" for f in r["findings"])
    files = [m for m in r["meter"] if m["channel"] == "Shared files"][0]
    assert files["bits_per_use"] > 0.9 and r["mole"]["landed"] >= 4
    assert r["verify"]["ok"] is None


def test_slip_taints_only_later_findings(runs):
    r = runs["slip"]
    st = [f["status"] for f in r["findings"]]
    assert st[:4] == ["VALID"] * 4 and st[4:] == ["TAINTED"] * 4 and r["first_leak_at"] == 5
    assert r["verify"]["ok"] is True


@pytest.mark.parametrize("mode", ["naive", "cleanroom", "slip"])
def test_committed_dashboard_data_has_the_same_shape(mode):
    """The sample runs the dashboard ships must follow the same contract."""
    path = ROOT / "dashboard" / "data" / f"{mode}.json"
    if not path.exists():
        pytest.skip(f"{path} is not committed yet")
    r = check_shape(json.loads(path.read_text()))
    assert r["mode"] == mode
    if r["diary"]["entries"]:
        assert verify(r["diary"])[0] is True
