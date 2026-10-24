from core.taint import status_for_findings, receipt


def test_no_leak():
    assert set(status_for_findings(8, None)) == {"VALID"}


def test_leak_at_five():
    s = status_for_findings(8, 4)
    assert s[:4] == ["VALID"] * 4 and s[4:] == ["TAINTED"] * 4


def test_leak_at_start():
    assert set(status_for_findings(8, 0)) == {"TAINTED"}


def test_receipt():
    assert receipt("a" * 64) == "a" * 10 and receipt(None) is None
