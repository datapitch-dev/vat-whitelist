"""Normalisation and checksum validation of NIP numbers and bank accounts."""

from __future__ import annotations

import re

_NIP_WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)


def normalize_nip(raw: object) -> str:
    """Strip spaces, dashes and a leading ``PL`` prefix: ``PL 526-025-02-74`` -> ``5260250274``."""
    text = str(raw or "").strip().upper()
    if text.endswith(".0"):  # NIP read from Excel as a float
        text = text[:-2]
    text = text.removeprefix("PL")
    return re.sub(r"[\s\-.]", "", text)


def is_valid_nip(nip: str) -> bool:
    """Check length and the NIP control digit (weighted sum modulo 11)."""
    if len(nip) != 10 or not nip.isdigit():
        return False
    checksum = sum(int(d) * w for d, w in zip(nip[:9], _NIP_WEIGHTS, strict=True)) % 11
    return checksum != 10 and checksum == int(nip[9])


def normalize_account(raw: object) -> str:
    """Return a bare 26-digit NRB: strips spaces, dashes and a ``PL`` IBAN prefix."""
    text = re.sub(r"[\s\-]", "", str(raw or "").strip().upper())
    return text.removeprefix("PL")


def is_valid_account(account: str) -> bool:
    """Validate a Polish NRB with the IBAN mod-97 check."""
    if len(account) != 26 or not account.isdigit():
        return False
    # IBAN: move "PL" + check digits to the end, letters P=25, L=21.
    rearranged = account[2:] + "2521" + account[:2]
    return int(rearranged) % 97 == 1
