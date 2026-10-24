"""Leak Meter: how many bits per second could leak through a channel?

Mutual information I(X;Y) between what red sent and what blue decoded, with the
Miller-Madow small-sample correction.
"""
import math


def mutual_information(n):
    """n is a 2x2 table of counts: n[sent_bit][decoded_bit]. Returns bits per use."""
    total = sum(sum(row) for row in n)
    if total == 0:
        return 0.0
    px = [sum(n[0]), sum(n[1])]
    py = [n[0][0] + n[1][0], n[0][1] + n[1][1]]
    m = 0.0
    for x in (0, 1):
        for y in (0, 1):
            if n[x][y] > 0:
                m += n[x][y] / total * math.log2(n[x][y] * total / (px[x] * py[y]))
    r = sum(1 for v in px if v > 0)
    c = sum(1 for v in py if v > 0)
    m -= (r - 1) * (c - 1) / (2 * total * math.log(2))
    return max(0.0, m)


def bits_per_second(bits_per_use, uses_per_s):
    return bits_per_use * uses_per_s


def key_seconds(bps, key_bits=256):
    """Seconds to leak a 32-character (256-bit) key. None when there is no usable signal."""
    return None if bps < 0.05 else key_bits / bps
