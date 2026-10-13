"""T1 — checksum เลขประจำตัวประชาชนไทย (mod-11)"""
import random

import pytest

from common.crypto import mask_natid, normalize_natid, valid_thai_id


def _make_valid(rng: random.Random) -> str:
    base = "".join(rng.choice("0123456789") for _ in range(12))
    total = sum(int(base[i]) * (13 - i) for i in range(12))
    return base + str((11 - total % 11) % 10)


@pytest.fixture
def rng():
    return random.Random(20260822)


def test_valid_ids_accepted(rng):
    for _ in range(200):
        assert valid_thai_id(_make_valid(rng))


def test_wrong_check_digit_rejected(rng):
    for _ in range(200):
        nid = _make_valid(rng)
        broken = nid[:12] + str((int(nid[12]) + 1) % 10)
        assert not valid_thai_id(broken)


@pytest.mark.parametrize("bad", ["", "123", "12345678901234", "abcdefghijklm",
                                 "1234-5678-9012", None])
def test_malformed_rejected(bad):
    assert not valid_thai_id(bad or "")


def test_separators_are_tolerated(rng):
    nid = _make_valid(rng)
    formatted = f"{nid[0]}-{nid[1:5]}-{nid[5:10]}-{nid[10:12]}-{nid[12]}"
    assert valid_thai_id(formatted)
    assert normalize_natid(formatted) == nid


def test_mask_hides_middle_digits():
    assert mask_natid("1234567890123") == "1-2345-XXXXX-XX-3"
    assert mask_natid("bad") == "X-XXXX-XXXXX-XX-X"


def test_thai_digits_converted_other_digits_rejected(rng):
    # เลขไทยแปลงเป็น 0-9 (คนเดียวกันต้องได้ natid_hash เดียวกัน) · เลขอารบิกไม่นับเป็นตัวเลข
    nid = _make_valid(rng)
    thai = "".join("๐๑๒๓๔๕๖๗๘๙"[int(c)] for c in nid)
    assert normalize_natid(thai) == nid and valid_thai_id(thai)
    arabic = "".join("٠١٢٣٤٥٦٧٨٩"[int(c)] for c in nid)
    assert arabic.isdigit() and not valid_thai_id(arabic) and normalize_natid(arabic) == ""
    assert normalize_natid("1-2345-67890-12-3") == "1234567890123"
