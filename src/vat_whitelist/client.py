"""Thin client for the VAT white list API (https://wl-api.mf.gov.pl)."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

import requests

BASE_URL = "https://wl-api.mf.gov.pl"
MAX_BATCH = 30  # the API accepts at most 30 NIPs per search request

# "Database has been updated, send again" and "Database is being updated, try later".
_RETRYABLE_CODES = {"WL-195", "WL-196"}


class ApiError(Exception):
    """Error returned by the API (``code`` is the WL-xxx code when present)."""

    def __init__(self, message: str, code: str | None = None, status: int | None = None):
        super().__init__(f"{code}: {message}" if code else message)
        self.code = code
        self.status = status


class LimitExceeded(ApiError):
    """The daily request limit of the API has been used up."""


@dataclass
class SearchResult:
    request_id: str
    subjects: dict[str, list[dict]] = field(default_factory=dict)


class WhiteListClient:
    """Calls ``/api/search/nips`` with retries on transient errors.

    ``session`` and ``sleep`` are injectable so tests run without network or waiting.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        base_url: str = BASE_URL,
        timeout: float = 30,
        retries: int = 3,
        backoff: float = 2.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.sleep = sleep

    def search_nips(self, nips: Iterable[str], date: str) -> SearchResult:
        nips = list(nips)
        if not 1 <= len(nips) <= MAX_BATCH:
            raise ValueError(f"search_nips takes 1-{MAX_BATCH} NIPs, got {len(nips)}")
        url = f"{self.base_url}/api/search/nips/{','.join(nips)}"
        result = self._get(url, {"date": date})
        return _parse_search(result, nips)

    def _get(self, url: str, params: dict) -> dict:
        for attempt in range(self.retries + 1):
            last = attempt == self.retries
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                if last:
                    raise ApiError(f"Brak połączenia z API: {exc}") from exc
                self.sleep(self.backoff * 2**attempt)
                continue

            if response.status_code == 429:
                raise LimitExceeded(
                    "Wyczerpany dzienny limit zapytań API", status=response.status_code
                )
            body = _json_or_none(response)
            if response.ok and body and "result" in body:
                return body["result"]

            code, message = _error_details(body, response)
            if (code in _RETRYABLE_CODES or response.status_code >= 500) and not last:
                self.sleep(self.backoff * 2**attempt)
                continue
            raise ApiError(message, code=code, status=response.status_code)
        raise AssertionError("unreachable")


def _json_or_none(response: requests.Response) -> dict | None:
    try:
        body = response.json()
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _error_details(body: dict | None, response: requests.Response) -> tuple[str | None, str]:
    if body and "code" in body:
        return body["code"], body.get("message", "")
    return None, f"HTTP {response.status_code}: {response.text[:200]}"


def _parse_search(result: dict, nips: list[str]) -> SearchResult:
    """Map the response to ``{nip: [subject, ...]}``.

    Current API versions return ``entries`` (one per requested identifier); older ones a flat
    ``subjects`` list. Both are accepted.
    """
    out = SearchResult(request_id=result.get("requestId", ""))
    out.subjects = {nip: [] for nip in nips}
    if "entries" in result:
        for entry in result.get("entries") or []:
            identifier = entry.get("identifier")
            if identifier in out.subjects:
                out.subjects[identifier] = [s for s in entry.get("subjects") or [] if s]
    else:
        for subject in result.get("subjects") or []:
            if subject and subject.get("nip") in out.subjects:
                out.subjects[subject["nip"]].append(subject)
    return out
