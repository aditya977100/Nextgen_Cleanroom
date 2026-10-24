"""Tripwire words ("canaries"): unique strings we hide, then search for."""
import re
import secrets

PATTERN = re.compile(r"CNRY-[0-9a-f]{8}")


def make_canaries():
    return {"red": "CNRY-" + secrets.token_hex(4), "blue": "CNRY-" + secrets.token_hex(4)}


def find(text):
    return PATTERN.findall(text)
