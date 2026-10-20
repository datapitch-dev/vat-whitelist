"""Offline stand-in for the API, so the tool can be tried (and tested in CI) without network.

The NIPs in ``examples/kontrahenci.csv`` start with 000, a tax office code that does not exist,
so they never point at a real company.
"""

from __future__ import annotations

import json
import uuid
from urllib.parse import unquote

_SUBJECTS = {
    "0004182736": {
        "name": "HURTOWNIA ALFA SP. Z O.O. (DEMO)",
        "statusVat": "Czynny",
        "regon": "000418273",
        "krs": "0000111111",
        "workingAddress": "UL. PRZYKŁADOWA 1, 00-001 WARSZAWA",
        "registrationLegalDate": "2015-03-02",
        "accountNumbers": ["60102010260000042270201111"],
        "hasVirtualAccounts": False,
    },
    "0006391823": {
        "name": "TRANSPORT BETA S.A. (DEMO)",
        "statusVat": "Czynny",
        "regon": "000639182",
        "workingAddress": "UL. TESTOWA 7, 30-002 KRAKÓW",
        "registrationLegalDate": "2018-11-15",
        "accountNumbers": ["46249000050000460000231234"],
        "hasVirtualAccounts": False,
    },
    "0007419363": {
        "name": "SERWIS GAMMA SP. Z O.O. (DEMO)",
        "statusVat": "Czynny",
        "regon": "000741936",
        "workingAddress": "UL. WZOROWA 3, 50-003 WROCŁAW",
        "registrationLegalDate": "2020-06-01",
        "accountNumbers": ["55124010370000999988887777"],
        "hasVirtualAccounts": True,
    },
    "0008524174": {
        "name": "BIURO DELTA JAN PRZYKŁADOWY (DEMO)",
        "statusVat": "Zwolniony",
        "residenceAddress": "UL. DEMO 12, 80-004 GDAŃSK",
        "registrationLegalDate": "2021-01-04",
        "accountNumbers": [],
        "hasVirtualAccounts": False,
    },
    "0001748290": {
        "name": "DRUKARNIA ZETA SP. J. (DEMO)",
        "statusVat": "Czynny",
        "regon": "000174829",
        "workingAddress": "UL. PRÓBNA 9, 60-005 POZNAŃ",
        "registrationLegalDate": "2012-09-17",
        "accountNumbers": ["10105000997603123456789123"],
        "hasVirtualAccounts": False,
    },
    "0003961473": {
        "name": "SKLEP ETA ANNA PRZYKŁADOWA (DEMO)",
        "statusVat": "Niezarejestrowany",
        "residenceAddress": "UL. MOCK 5, 90-006 ŁÓDŹ",
        "registrationLegalDate": "2016-05-10",
        "removalDate": "2024-02-29",
        "removalBasis": "Art. 96 ust. 9 ustawy o VAT",
        "accountNumbers": [],
        "hasVirtualAccounts": False,
    },
}


class _Response:
    def __init__(self, payload: dict, status_code: int = 200):
        self.status_code = status_code
        self.ok = status_code < 400
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class DemoSession:
    """Answers ``/api/search/nips/...`` like the real API, from the fixtures above."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str, params: dict | None = None, timeout: float | None = None):
        self.calls.append(url)
        nips = unquote(url.rsplit("/", 1)[1]).split(",")
        entries = []
        for nip in nips:
            subject = _SUBJECTS.get(nip)
            entries.append(
                {"identifier": nip, "subjects": [{"nip": nip, **subject}] if subject else []}
            )
        return _Response(
            {
                "result": {
                    "entries": entries,
                    "requestDateTime": f"{(params or {}).get('date', '')}",
                    "requestId": f"DEMO-{uuid.uuid4().hex[:10]}",
                }
            }
        )
