"""Core logic: validate input, batch NIPs, respect the request budget, build result rows."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .cache import Cache
from .client import MAX_BATCH, ApiError, LimitExceeded, WhiteListClient
from .identifiers import is_valid_account, is_valid_nip, normalize_account, normalize_nip

STATUS_INVALID_NIP = "Błędny NIP"
STATUS_NOT_FOUND = "Brak w wykazie"
STATUS_PENDING = "Nie sprawdzono"


@dataclass
class InputRow:
    nip: str
    account: str = ""


@dataclass
class Result:
    input_nip: str
    nip: str
    status: str
    name: str = ""
    regon: str = ""
    krs: str = ""
    address: str = ""
    registration_date: str = ""
    removal_date: str = ""
    accounts: list[str] = field(default_factory=list)
    has_virtual_accounts: bool = False
    input_account: str = ""
    account_on_list: str = ""
    request_id: str = ""
    note: str = ""

    @property
    def is_active(self) -> bool:
        return self.status == "Czynny"


@dataclass
class RunStats:
    requests_used: int = 0
    from_cache: int = 0
    stopped_reason: str = ""


def check(
    rows: Iterable[InputRow],
    client: WhiteListClient,
    cache: Cache,
    date: str,
    max_requests_per_day: int = 100,
    progress: Callable[[int, int], None] | None = None,
) -> tuple[list[Result], RunStats]:
    rows = list(rows)
    stats = RunStats()
    nips = [normalize_nip(r.nip) for r in rows]

    lookups: dict[str, tuple[str, list[dict]]] = {}
    todo: list[str] = []
    for nip in dict.fromkeys(nips):  # unique, order kept
        if not is_valid_nip(nip):
            continue
        cached = cache.get(nip, date)
        if cached is not None:
            lookups[nip] = cached
            stats.from_cache += 1
        else:
            todo.append(nip)

    batches = [todo[i : i + MAX_BATCH] for i in range(0, len(todo), MAX_BATCH)]
    for done, batch in enumerate(batches, start=1):
        if cache.requests_today() >= max_requests_per_day:
            stats.stopped_reason = (
                f"Osiągnięto limit {max_requests_per_day} zapytań na dziś. "
                "Uruchom ponownie jutro, sprawdzone NIP-y są w pamięci podręcznej."
            )
            break
        try:
            found = client.search_nips(batch, date)
        except LimitExceeded as exc:
            stats.stopped_reason = f"{exc}. Uruchom ponownie jutro."
            break
        except ApiError as exc:
            stats.stopped_reason = f"Błąd API: {exc}"
            break
        cache.count_request()
        stats.requests_used += 1
        for nip, subjects in found.subjects.items():
            cache.put(nip, date, found.request_id, subjects)
            lookups[nip] = (found.request_id, subjects)
        if progress:
            progress(done, len(batches))

    results = [
        _build_result(row, nip, lookups.get(nip)) for row, nip in zip(rows, nips, strict=True)
    ]
    return results, stats


def _build_result(row: InputRow, nip: str, lookup: tuple[str, list[dict]] | None) -> Result:
    result = Result(input_nip=str(row.nip), nip=nip, status=STATUS_PENDING)
    if not is_valid_nip(nip):
        result.status = STATUS_INVALID_NIP
        result.note = "Zła długość lub cyfra kontrolna"
        return result
    if lookup is None:
        return result

    request_id, subjects = lookup
    result.request_id = request_id
    if not subjects:
        result.status = STATUS_NOT_FOUND
        return result

    subject = subjects[0]
    if len(subjects) > 1:
        result.note = f"W wykazie {len(subjects)} podmioty z tym NIP-em, pokazano pierwszy"
    result.status = subject.get("statusVat") or STATUS_NOT_FOUND
    result.name = subject.get("name") or ""
    result.regon = subject.get("regon") or ""
    result.krs = subject.get("krs") or ""
    result.address = subject.get("workingAddress") or subject.get("residenceAddress") or ""
    result.registration_date = subject.get("registrationLegalDate") or ""
    result.removal_date = subject.get("removalDate") or ""
    result.accounts = list(subject.get("accountNumbers") or [])
    result.has_virtual_accounts = bool(subject.get("hasVirtualAccounts"))
    if subject.get("removalBasis"):
        result.note = _join(result.note, f"Podstawa wykreślenia: {subject['removalBasis']}")

    if row.account:
        _check_account(result, normalize_account(row.account))
    return result


def _check_account(result: Result, account: str) -> None:
    result.input_account = account
    if not is_valid_account(account):
        result.account_on_list = "Błędny numer"
    elif account in result.accounts:
        result.account_on_list = "TAK"
    elif result.has_virtual_accounts:
        # Virtual (masked) accounts are not listed in full, so absence here is not conclusive.
        result.account_on_list = "Sprawdź ręcznie"
        result.note = _join(result.note, "Firma ma rachunki wirtualne")
    else:
        result.account_on_list = "NIE"


def _join(*parts: str) -> str:
    return "; ".join(p for p in parts if p)
