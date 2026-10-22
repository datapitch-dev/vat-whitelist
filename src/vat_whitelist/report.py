"""Excel and CSV reports.

The Excel workbook is meant to be handed over as is: a summary sheet first, then the results
and the full list of bank accounts, in one consistent visual style, ready to print.
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date as date_cls
from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .checker import STATUS_INVALID_NIP, STATUS_PENDING, Result, RunStats

# --- palette and type ---------------------------------------------------------------------

NAVY = "1F3A5F"
GOLD = "C9A227"
INK = "1B2430"
MUTED = "6B7280"
LINE = "D9DEE5"
BAND = "F5F7FA"
FONT = "Calibri"

_THIN = Side(style="thin", color=LINE)
_ROW_BORDER = Border(bottom=_THIN)
_HEADER_BORDER = Border(bottom=Side(style="medium", color=GOLD))


@dataclass(frozen=True)
class Tone:
    fill: str
    text: str


TONES = {
    "OK": Tone("E3F1E7", "1E6B3A"),
    "Do weryfikacji": Tone("FDF1DC", "8A5300"),
    "Problem": Tone("FBE4E4", "9B1C1C"),
    "Nie sprawdzono": Tone("EDEFF2", "4B5563"),
}

VERDICT_HELP = {
    "OK": "czynny podatnik VAT; rachunek z pliku (jeśli podany) jest w wykazie",
    "Do weryfikacji": "zwolniony z VAT albo rachunek nie do sprawdzenia automatycznie "
    "(firma ma rachunki wirtualne)",
    "Problem": "brak w wykazie, wykreślony, błędny NIP lub rachunek spoza wykazu",
    "Nie sprawdzono": "skończył się dzienny limit zapytań; uruchom ponownie jutro",
}


def verdict(result: Result) -> str:
    if result.status == STATUS_PENDING:
        return "Nie sprawdzono"
    if result.account_on_list in ("NIE", "Błędny numer"):
        return "Problem"
    if result.is_active:
        return "Do weryfikacji" if result.account_on_list == "Sprawdź ręcznie" else "OK"
    return "Do weryfikacji" if result.status == "Zwolniony" else "Problem"


def status_tone(result: Result) -> Tone:
    if result.is_active:
        return TONES["OK"]
    if result.status == "Zwolniony":
        return TONES["Do weryfikacji"]
    if result.status == STATUS_PENDING:
        return TONES["Nie sprawdzono"]
    return TONES["Problem"]


def account_tone(value: str) -> Tone | None:
    return {
        "TAK": TONES["OK"],
        "Sprawdź ręcznie": TONES["Do weryfikacji"],
        "NIE": TONES["Problem"],
        "Błędny numer": TONES["Problem"],
    }.get(value)


def format_account(account: str) -> str:
    """26-digit NRB in the usual grouping: ``60 1020 1026 0000 0422 7020 1111``."""
    if len(account) != 26 or not account.isdigit():
        return account
    return account[:2] + " " + " ".join(account[i : i + 4] for i in range(2, 26, 4))


def _as_date(value: str) -> date_cls | None:
    try:
        return date_cls.fromisoformat(value) if value else None
    except ValueError:
        return None


# --- columns ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Column:
    header: str
    get: Callable[[Result], object]
    width: float
    kind: str = "text"  # text | wrap | date | count | code | muted
    tone: Callable[[Result], Tone | None] | None = None


COLUMNS = [
    Column("Kontrahent (nazwa z wykazu)", lambda r: r.name or None, 40, "wrap"),
    Column("NIP", lambda r: r.nip, 13, "code"),
    Column("Ocena", verdict, 16, "pill", lambda r: TONES[verdict(r)]),
    Column("Status VAT", lambda r: r.status, 19, "pill", status_tone),
    Column("Rachunek z pliku", lambda r: format_account(r.input_account) or None, 34, "code"),
    Column(
        "Rachunek w wykazie",
        lambda r: r.account_on_list or None,
        17,
        "pill",
        lambda r: account_tone(r.account_on_list),
    ),
    Column("REGON", lambda r: r.regon or None, 12, "code"),
    Column("KRS", lambda r: r.krs or None, 12, "code"),
    Column("Adres", lambda r: r.address or None, 34, "wrap"),
    Column("Data rejestracji", lambda r: _as_date(r.registration_date), 13, "date"),
    Column("Data wykreślenia", lambda r: _as_date(r.removal_date), 13, "date"),
    Column("Rachunków w wykazie", lambda r: len(r.accounts) or None, 12, "count"),
    Column("Rachunki wirtualne", lambda r: "tak" if r.has_virtual_accounts else None, 11, "count"),
    Column("Id zapytania MF", lambda r: r.request_id or None, 17, "code"),
    Column("Uwagi", lambda r: r.note or None, 32, "wrap"),
    Column("NIP w pliku", lambda r: r.input_nip, 18, "muted"),
]


def visible_columns(results: list[Result]) -> list[Column]:
    """Leave out columns that would be empty for the whole file, to keep the sheet narrow."""
    has_accounts = any(r.input_account for r in results)
    reformatted = any(r.input_nip.strip() != r.nip for r in results)
    hidden = set()
    if not has_accounts:
        hidden |= {"Rachunek z pliku", "Rachunek w wykazie"}
    if not reformatted:
        hidden.add("NIP w pliku")
    return [c for c in COLUMNS if c.header not in hidden]


# --- styling helpers ----------------------------------------------------------------------


def _font(size: float = 10, bold: bool = False, color: str = INK, **kw) -> Font:
    return Font(name=FONT, size=size, bold=bold, color=color, **kw)


def _fill(color: str) -> PatternFill:
    return PatternFill("solid", fgColor=color)


def _title(ws: Worksheet, title: str, subtitle: str, col: int = 1) -> None:
    ws.cell(1, col, title).font = Font(name="Calibri Light", size=18, color=NAVY)
    ws.cell(2, col, subtitle).font = _font(10, color=MUTED)
    ws.row_dimensions[1].height = 30
    ws.row_dimensions[2].height = 18


def _header_row(
    ws: Worksheet, row: int, headers: list[str], centered: set[int] = frozenset()
) -> None:
    for i, text in enumerate(headers):
        cell = ws.cell(row, 1 + i, text)
        cell.font = _font(10, bold=True, color="FFFFFF")
        cell.fill = _fill(NAVY)
        cell.border = _HEADER_BORDER
        cell.alignment = Alignment(
            horizontal="center" if i in centered else None, vertical="center", wrap_text=True
        )
    ws.row_dimensions[row].height = 32


def _page_setup(ws: Worksheet, landscape: bool, title_rows: str | None, footer_left: str) -> None:
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins.left = ws.page_margins.right = 0.4
    ws.page_margins.top = ws.page_margins.bottom = 0.6
    ws.print_options.horizontalCentered = True
    if title_rows:
        ws.print_title_rows = title_rows
    ws.oddFooter.left.text = footer_left
    ws.oddFooter.left.size = 8
    ws.oddFooter.right.text = "Strona &P z &N"
    ws.oddFooter.right.size = 8


# --- sheets -------------------------------------------------------------------------------


def summary(results: list[Result]) -> Counter:
    counts = Counter(r.status for r in results)
    for r in results:
        if r.account_on_list:
            counts[f"Rachunek: {r.account_on_list}"] += 1
    return counts


def _results_sheet(ws: Worksheet, results: list[Result], subtitle: str, footer: str) -> None:
    _title(ws, "Wyniki weryfikacji", subtitle)
    columns = visible_columns(results)
    header_row = 4
    centered = {0} | {
        i for i, c in enumerate(columns, start=1) if c.kind in ("pill", "date", "count")
    }
    _header_row(ws, header_row, ["Lp.", *(c.header for c in columns)], centered)
    ws.column_dimensions["A"].width = 6
    for i, col in enumerate(columns, start=2):
        ws.column_dimensions[get_column_letter(i)].width = col.width

    for n, result in enumerate(results, start=1):
        row = header_row + n
        band = _fill(BAND) if n % 2 == 0 else None
        lp = ws.cell(row, 1, n)
        lp.font = _font(9, color=MUTED)
        lp.alignment = Alignment(horizontal="center", vertical="center")
        for i, col in enumerate(columns, start=2):
            cell = ws.cell(row, i, col.get(result))
            cell.border = _ROW_BORDER
            cell.font = _font(10)
            cell.alignment = Alignment(vertical="center")
            if band:
                cell.fill = band
            if col.kind == "wrap":
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                if i == 2 and cell.value is None:
                    cell.value = {
                        STATUS_INVALID_NIP: "nie sprawdzono, błędny NIP",
                        STATUS_PENDING: "nie sprawdzono",
                    }.get(result.status, "nie figuruje w wykazie")
                    cell.font = _font(10, color=MUTED, italic=True)
            elif col.kind == "date":
                cell.number_format = "DD.MM.YYYY"
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col.kind == "count":
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col.kind == "muted":
                cell.font = _font(9, color=MUTED)
            elif col.kind == "pill" and cell.value is not None:
                tone = col.tone(result) if col.tone else None
                if tone:
                    cell.fill = _fill(tone.fill)
                    cell.font = _font(10, bold=True, color=tone.text)
                cell.alignment = Alignment(horizontal="center", vertical="center")
        lp.border = _ROW_BORDER
        if band:
            lp.fill = band
        ws.row_dimensions[row].height = 30

    last_col = get_column_letter(len(columns) + 1)
    last_row = header_row + max(len(results), 1)
    ws.auto_filter.ref = f"A{header_row}:{last_col}{last_row}"
    ws.freeze_panes = ws.cell(header_row + 1, 4)  # keep Lp., name and NIP in view
    _page_setup(ws, landscape=True, title_rows=f"{header_row}:{header_row}", footer_left=footer)


def _accounts_sheet(ws: Worksheet, results: list[Result], subtitle: str, footer: str) -> None:
    _title(ws, "Rachunki bankowe z wykazu", subtitle)
    header_row = 4
    _header_row(ws, header_row, ["Lp.", "Kontrahent", "NIP", "Rachunek"], {0})
    for col, width in zip("ABCD", (6, 50, 13, 36), strict=True):
        ws.column_dimensions[col].width = width

    row, seen = header_row, set()
    for result in results:
        if result.nip in seen or not result.accounts:
            continue
        seen.add(result.nip)
        for account in result.accounts:
            row += 1
            n = row - header_row
            values = [n, result.name, result.nip, format_account(account)]
            for i, value in enumerate(values, start=1):
                cell = ws.cell(row, i, value)
                cell.font = _font(9, color=MUTED) if i == 1 else _font(10)
                cell.border = _ROW_BORDER
                cell.alignment = Alignment(
                    horizontal="center" if i == 1 else None, vertical="center"
                )
                if n % 2 == 0:
                    cell.fill = _fill(BAND)
    if row == header_row:
        ws.cell(header_row + 1, 2, "Żaden kontrahent nie ma rachunków w wykazie.").font = _font(
            10, color=MUTED, italic=True
        )
    ws.auto_filter.ref = f"A{header_row}:D{max(row, header_row + 1)}"
    ws.freeze_panes = ws.cell(header_row + 1, 1)
    _page_setup(ws, landscape=False, title_rows=f"{header_row}:{header_row}", footer_left=footer)


def _summary_sheet(
    ws: Worksheet, results: list[Result], stats: RunStats, check_date: date_cls, footer: str
) -> None:
    ws.column_dimensions["A"].width = 2
    ws.column_dimensions["B"].width = 16
    for col in "CDEFGHIJ":
        ws.column_dimensions[col].width = 14
    _title(
        ws,
        "Weryfikacja kontrahentów na białej liście VAT",
        f"Stan na dzień {check_date:%d.%m.%Y} · Wykaz podatników VAT, Ministerstwo Finansów",
        col=2,
    )
    for col in range(2, 11):
        ws.cell(3, col).border = Border(bottom=Side(style="medium", color=GOLD))
    ws.row_dimensions[3].height = 6

    verdicts = Counter(verdict(r) for r in results)
    tiles = [("Kontrahentów", len(results), NAVY)]
    tiles += [(name, verdicts.get(name, 0), TONES[name].text) for name in ("OK", "Do weryfikacji")]
    tiles += [("Problem", verdicts.get("Problem", 0), TONES["Problem"].text)]
    if verdicts.get("Nie sprawdzono"):
        tiles.append(("Nie sprawdzono", verdicts["Nie sprawdzono"], TONES["Nie sprawdzono"].text))
    row_num, row_label = 5, 6
    for i, (label, value, color) in enumerate(tiles):
        c1 = 2 + i * 2
        ws.merge_cells(start_row=row_num, start_column=c1, end_row=row_num, end_column=c1 + 1)
        ws.merge_cells(start_row=row_label, start_column=c1, end_row=row_label, end_column=c1 + 1)
        num = ws.cell(row_num, c1, value)
        num.font = _font(24, bold=True, color=color)
        num.alignment = Alignment(horizontal="left", vertical="bottom", indent=1)
        lab = ws.cell(row_label, c1, label)
        lab.font = _font(9, color=MUTED)
        lab.alignment = Alignment(horizontal="left", vertical="top", indent=1)
        for c in (c1, c1 + 1):
            ws.cell(row_num, c).fill = _fill(BAND)
            ws.cell(row_label, c).fill = _fill(BAND)
            ws.cell(row_num, c).border = Border(top=Side(style="thick", color=color))
    ws.row_dimensions[4].height = 10
    ws.row_dimensions[row_num].height = 38
    ws.row_dimensions[row_label].height = 20

    row = 8
    row = _table(
        ws,
        row,
        "Status VAT",
        sorted(Counter(r.status for r in results).items(), key=lambda kv: -kv[1]),
        len(results),
    )
    accounts = Counter(r.account_on_list for r in results if r.account_on_list)
    if accounts:
        row = _table(
            ws,
            row + 1,
            "Rachunek z pliku w wykazie",
            accounts.most_common(),
            sum(accounts.values()),
        )

    row += 1
    _section(ws, row, "Ocena: co oznacza")
    for name, help_text in VERDICT_HELP.items():
        if name == "Nie sprawdzono" and not verdicts.get(name):
            continue
        row += 1
        pill = ws.cell(row, 2, name)
        pill.font = _font(9, bold=True, color=TONES[name].text)
        pill.fill = _fill(TONES[name].fill)
        pill.alignment = Alignment(horizontal="center", vertical="center")
        ws.merge_cells(start_row=row, start_column=3, end_row=row, end_column=10)
        text = ws.cell(row, 3, help_text)
        text.font = _font(10)
        text.alignment = Alignment(vertical="center", indent=1)
        ws.row_dimensions[row].height = 20

    row += 2
    _section(ws, row, "Przebieg")
    unique = len({r.nip for r in results})
    info = [
        ("Stan na dzień", check_date, "DD.MM.YYYY"),
        ("Wygenerowano", datetime.now().replace(second=0, microsecond=0), "DD.MM.YYYY HH:MM"),
        ("Unikalnych NIP-ów", unique, "0"),
        ("Zapytań do API MF", stats.requests_used, "0"),
        ("Z pamięci podręcznej", stats.from_cache, "0"),
    ]
    for label, value, fmt in info:
        row += 1
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
        ws.merge_cells(start_row=row, start_column=5, end_row=row, end_column=7)
        ws.cell(row, 2, label).font = _font(10, color=MUTED)
        cell = ws.cell(row, 5, value)
        cell.font = _font(10)
        cell.number_format = fmt
        cell.alignment = Alignment(horizontal="left")
    if stats.stopped_reason:
        row += 1
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=10)
        cell = ws.cell(row, 2, f"Uwaga: {stats.stopped_reason}")
        cell.font = _font(10, bold=True, color=TONES["Problem"].text)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[row].height = 30

    row += 2
    ws.merge_cells(start_row=row, start_column=2, end_row=row + 1, end_column=10)
    note = ws.cell(
        row,
        2,
        "Kolumna „Id zapytania MF” w arkuszu Wyniki zawiera identyfikator nadany przez "
        "Ministerstwo Finansów. Potwierdza on, że kontrahent został sprawdzony w wykazie "
        "w podanym dniu. Raport nie stanowi porady podatkowej.",
    )
    note.font = _font(9, color=MUTED, italic=True)
    note.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[row].height = 18
    ws.row_dimensions[row + 1].height = 18
    _page_setup(ws, landscape=False, title_rows=None, footer_left=footer)


def _section(ws: Worksheet, row: int, title: str) -> None:
    cell = ws.cell(row, 2, title)
    cell.font = _font(11, bold=True, color=NAVY)
    ws.row_dimensions[row].height = 22


def _table(ws: Worksheet, row: int, title: str, items: list[tuple[str, int]], total: int) -> int:
    _section(ws, row, title)
    row += 1
    for col, (text, align) in enumerate(
        (("Wynik", "left"), ("", None), ("", None), ("Liczba", "right"), ("Udział", "right")),
        start=2,
    ):
        cell = ws.cell(row, col, text)
        cell.font = _font(9, bold=True, color=MUTED)
        cell.border = Border(bottom=Side(style="thin", color=MUTED))
        if align:
            cell.alignment = Alignment(horizontal=align)
    for key, count in items:
        row += 1
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
        ws.cell(row, 2, key).font = _font(10)
        ws.cell(row, 5, count).font = _font(10)
        share = ws.cell(row, 6, count / total if total else 0)
        share.font = _font(10)
        share.number_format = "0.0%"
        for col in range(2, 7):
            ws.cell(row, col).border = _ROW_BORDER
    row += 1
    ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
    ws.cell(row, 2, "Razem").font = _font(10, bold=True)
    ws.cell(row, 5, total).font = _font(10, bold=True)
    share = ws.cell(row, 6, 1 if total else 0)
    share.font = _font(10, bold=True)
    share.number_format = "0.0%"
    return row + 1


def write_xlsx(results: list[Result], stats: RunStats, path: str | Path, date: str) -> None:
    check_date = date_cls.fromisoformat(date)
    subtitle = f"Stan na dzień {check_date:%d.%m.%Y} · źródło: Wykaz podatników VAT (MF)"
    footer = f"Biała lista VAT · stan na {check_date:%d.%m.%Y}"

    wb = Workbook()
    wb.properties.creator = "vat-whitelist"
    wb.properties.title = "Weryfikacja kontrahentów na białej liście VAT"
    _summary_sheet(wb.active, results, stats, check_date, footer)
    wb.active.title = "Podsumowanie"
    _results_sheet(wb.create_sheet("Wyniki"), results, subtitle, footer)
    _accounts_sheet(wb.create_sheet("Rachunki"), results, subtitle, footer)
    wb.active = 0
    wb.save(path)


def write_csv(results: list[Result], path: str | Path) -> None:
    # Semicolon + BOM so Polish Excel opens it correctly with a double click.
    with Path(path).open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh, delimiter=";")
        writer.writerow([c.header for c in COLUMNS])
        for result in results:
            row = []
            for c in COLUMNS:
                value = c.get(result)
                if isinstance(value, date_cls):
                    value = value.isoformat()
                row.append("" if value is None else value)
            writer.writerow(row)
