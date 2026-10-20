import pytest

from vat_whitelist.identifiers import (
    is_valid_account,
    is_valid_nip,
    normalize_account,
    normalize_nip,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("526-025-02-74", "5260250274"),
        ("PL 526 025 02 74", "5260250274"),
        ("pl5260250274", "5260250274"),
        (5260250274.0, "5260250274"),
        (None, ""),
    ],
)
def test_normalize_nip(raw, expected):
    assert normalize_nip(raw) == expected


def test_nip_checksum():
    assert is_valid_nip("5260250274")  # Ministerstwo Finansów, published NIP
    assert is_valid_nip("0004182736")
    assert not is_valid_nip("5260250275")
    assert not is_valid_nip("1234567890")  # checksum 10 is never valid
    assert not is_valid_nip("526025027")
    assert not is_valid_nip("52602502AB")


def test_account_normalisation_and_checksum():
    account = normalize_account("PL60 1020 1026 0000 0422 7020 1111")
    assert account == "60102010260000042270201111"
    assert is_valid_account(account)
    assert not is_valid_account("61102010260000042270201111")
    assert not is_valid_account("12345")
