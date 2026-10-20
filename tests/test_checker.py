from tests.conftest import FakeResponse, ScriptedSession, entries_payload
from vat_whitelist.checker import (
    STATUS_INVALID_NIP,
    STATUS_NOT_FOUND,
    STATUS_PENDING,
    InputRow,
    check,
)
from vat_whitelist.client import WhiteListClient
from vat_whitelist.identifiers import is_valid_nip

DATE = "2026-10-20"
ACTIVE = {
    "name": "ALFA",
    "statusVat": "Czynny",
    "accountNumbers": ["60102010260000042270201111"],
    "hasVirtualAccounts": False,
}


def client(*responses):
    session = ScriptedSession(*responses)
    return WhiteListClient(session=session, sleep=lambda _: None), session


def test_statuses_dedup_and_account_match(cache):
    api, session = client(FakeResponse(entries_payload({"0004182736": ACTIVE, "0009637288": None})))
    rows = [
        InputRow("000-418-27-36", "PL60 1020 1026 0000 0422 7020 1111"),
        InputRow("0009637288"),
        InputRow("1234567890"),
        InputRow("0004182736", "19114020040000350230599137"),
    ]
    results, stats = check(rows, api, cache, DATE)

    assert len(session.calls) == 1  # invalid NIP skipped, duplicate asked once
    assert stats.requests_used == 1
    assert [r.status for r in results] == ["Czynny", STATUS_NOT_FOUND, STATUS_INVALID_NIP, "Czynny"]
    assert results[0].account_on_list == "TAK"
    assert results[3].account_on_list == "NIE"
    assert results[0].request_id == "REQ-1"


def test_virtual_accounts_are_not_reported_as_mismatch(cache):
    subject = {**ACTIVE, "hasVirtualAccounts": True}
    api, _ = client(FakeResponse(entries_payload({"0004182736": subject})))
    results, _ = check([InputRow("0004182736", "19114020040000350230599137")], api, cache, DATE)
    assert results[0].account_on_list == "Sprawdź ręcznie"


def test_second_run_uses_cache(cache):
    api, session = client(FakeResponse(entries_payload({"0004182736": ACTIVE})))
    check([InputRow("0004182736")], api, cache, DATE)
    results, stats = check([InputRow("0004182736")], api, cache, DATE)
    assert len(session.calls) == 1
    assert stats.from_cache == 1
    assert results[0].name == "ALFA"


def test_batches_of_30_and_budget_stop(cache):
    candidates = (f"{i:09d}{d}" for i in range(1, 200) for d in range(10))
    valid = list(dict.fromkeys(n for n in candidates if is_valid_nip(n)))
    valid = valid[:65]  # -> 3 batches: 30, 30, 5

    api, session = client(
        FakeResponse(entries_payload(dict.fromkeys(valid[:30], ACTIVE), "R1")),
        FakeResponse(entries_payload(dict.fromkeys(valid[30:60], ACTIVE), "R2")),
    )
    results, stats = check([InputRow(n) for n in valid], api, cache, DATE, max_requests_per_day=2)

    assert len(session.calls) == 2
    assert "limit 2" in stats.stopped_reason
    assert sum(r.status == STATUS_PENDING for r in results) == 5
    assert {r.request_id for r in results[:60]} == {"R1", "R2"}


def test_api_limit_response_stops_gracefully(cache):
    api, _ = client(FakeResponse(None, 429))
    results, stats = check([InputRow("0004182736")], api, cache, DATE)
    assert results[0].status == STATUS_PENDING
    assert "limit" in stats.stopped_reason
