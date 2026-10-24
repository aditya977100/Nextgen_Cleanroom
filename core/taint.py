"""Taint tracker: a leak at finding k taints finding k and every later one."""


def status_for_findings(n_findings, first_leak_index):
    """first_leak_index is 0-based (None = no leak). Returns a list of VALID / TAINTED."""
    return ["TAINTED" if first_leak_index is not None and i >= first_leak_index else "VALID"
            for i in range(n_findings)]


def receipt(entry_hash):
    """A finding's receipt is the first 10 characters of its diary entry hash."""
    return entry_hash[:10] if entry_hash else None


def summary(statuses):
    valid = statuses.count("VALID")
    total = len(statuses)
    if valid == total:
        return f"All {total} findings are trustworthy. Each has a receipt tied to the sealed diary."
    if valid == 0:
        return f"All {total} findings are tainted. Nothing can be trusted; re-run all {total}."
    return f"{valid} of {total} findings are still valid. Re-run only the {total - valid} tainted ones, not all {total}."
