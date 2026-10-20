import pytest
import requests

from tests.conftest import FakeResponse, ScriptedSession, entries_payload
from vat_whitelist.client import ApiError, LimitExceeded, WhiteListClient


def make_client(session):
    return WhiteListClient(session=session, sleep=lambda _: None)


def test_search_builds_url_and_parses_entries():
    session = ScriptedSession(
        FakeResponse(entries_payload({"0004182736": {"name": "A", "statusVat": "Czynny"}}))
    )
    result = make_client(session).search_nips(["0004182736", "0006391823"], "2026-10-20")

    url, params = session.calls[0]
    assert url.endswith("/api/search/nips/0004182736,0006391823")
    assert params == {"date": "2026-10-20"}
    assert result.request_id == "REQ-1"
    assert result.subjects["0004182736"][0]["statusVat"] == "Czynny"
    assert result.subjects["0006391823"] == []  # asked for but not returned


def test_search_accepts_legacy_flat_subjects():
    payload = {"result": {"subjects": [{"nip": "0004182736", "name": "A"}], "requestId": "R"}}
    result = make_client(ScriptedSession(FakeResponse(payload))).search_nips(
        ["0004182736"], "2026-10-20"
    )
    assert result.subjects["0004182736"][0]["name"] == "A"


def test_batch_size_is_enforced():
    with pytest.raises(ValueError):
        make_client(ScriptedSession()).search_nips(["0004182736"] * 31, "2026-10-20")


def test_retries_when_database_is_updating():
    session = ScriptedSession(
        FakeResponse({"code": "WL-196", "message": "Database is being updated"}, 400),
        FakeResponse(None, 503),
        FakeResponse(entries_payload({"0004182736": {"name": "A"}})),
    )
    result = make_client(session).search_nips(["0004182736"], "2026-10-20")
    assert len(session.calls) == 3
    assert result.subjects["0004182736"][0]["name"] == "A"


def test_retries_connection_errors_then_gives_up():
    session = ScriptedSession(*[requests.ConnectionError("down")] * 4)
    with pytest.raises(ApiError, match="Brak połączenia"):
        make_client(session).search_nips(["0004182736"], "2026-10-20")
    assert len(session.calls) == 4


def test_validation_error_is_not_retried():
    session = ScriptedSession(FakeResponse({"code": "WL-103", "message": "Future date"}, 400))
    with pytest.raises(ApiError) as exc:
        make_client(session).search_nips(["0004182736"], "2030-01-01")
    assert exc.value.code == "WL-103"
    assert len(session.calls) == 1


def test_http_429_means_daily_limit():
    with pytest.raises(LimitExceeded):
        make_client(ScriptedSession(FakeResponse(None, 429))).search_nips(
            ["0004182736"], "2026-10-20"
        )
