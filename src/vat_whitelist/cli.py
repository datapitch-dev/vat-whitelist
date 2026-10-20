"""Command line entry point: ``vat-whitelist kontrahenci.csv -o raport.xlsx``."""

from __future__ import annotations

import argparse
import sys
from datetime import date as date_cls
from pathlib import Path

from .cache import Cache
from .checker import check
from .client import WhiteListClient
from .demo import DemoSession
from .inputs import InputError, read_rows
from .report import summary, write_csv, write_xlsx


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vat-whitelist",
        description="Sprawdza listę kontrahentów na białej liście podatników VAT (API MF).",
    )
    parser.add_argument("plik", help="CSV lub XLSX z kolumną NIP (opcjonalnie z rachunkiem)")
    parser.add_argument(
        "-o", "--wynik", help="plik raportu .xlsx lub .csv (domyślnie raport_<data>.xlsx)"
    )
    parser.add_argument("--kolumna-nip", help="nazwa kolumny z NIP-em (domyślnie wykrywana)")
    parser.add_argument("--kolumna-rachunek", help="nazwa kolumny z rachunkiem do sprawdzenia")
    parser.add_argument(
        "--data", default=date_cls.today().isoformat(), help="stan na dzień, RRRR-MM-DD"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="maks. zapytań do API na dobę, po 30 NIP-ów każde (domyślnie 100)",
    )
    parser.add_argument("--cache", default=".vat_whitelist.sqlite", help="plik pamięci podręcznej")
    parser.add_argument("--demo", action="store_true", help="tryb demo bez internetu")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        date_cls.fromisoformat(args.data)
    except ValueError:
        print(f"Zła data {args.data!r}, użyj formatu RRRR-MM-DD", file=sys.stderr)
        return 2
    try:
        rows = read_rows(args.plik, args.kolumna_nip, args.kolumna_rachunek)
    except InputError as exc:
        print(exc, file=sys.stderr)
        return 2

    output = Path(args.wynik or f"raport_{args.data}.xlsx")
    client = WhiteListClient(session=DemoSession()) if args.demo else WhiteListClient()
    cache = Cache(":memory:" if args.demo else args.cache)
    print(f"Kontrahentów: {len(rows)}, stan na {args.data}{' (DEMO)' if args.demo else ''}")

    results, stats = check(
        rows,
        client,
        cache,
        args.data,
        max_requests_per_day=args.limit,
        progress=lambda done, total: print(f"  zapytanie {done}/{total}"),
    )
    cache.close()

    if output.suffix.lower() == ".csv":
        write_csv(results, output)
    else:
        write_xlsx(results, stats, output, args.data)

    for key, count in sorted(summary(results).items()):
        print(f"  {key}: {count}")
    print(f"Zapytań do API: {stats.requests_used}, z pamięci podręcznej: {stats.from_cache}")
    if stats.stopped_reason:
        print(f"UWAGA: {stats.stopped_reason}")
    print(f"Raport: {output}")
    return 1 if stats.stopped_reason else 0


if __name__ == "__main__":
    sys.exit(main())
