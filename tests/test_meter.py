from core.meter import mutual_information, key_seconds


def test_perfect_channel():
    assert mutual_information([[100, 0], [0, 100]]) > 0.95


def test_constant_decoder_is_zero():
    assert mutual_information([[100, 0], [100, 0]]) == 0.0


def test_key_time():
    assert key_seconds(0.0) is None and abs(key_seconds(40.0) - 6.4) < 1e-9
