from openpyxl import load_workbook

from vat_whitelist.cli import main
from vat_whitelist.inputs import read_rows


def test_reads_semicolon_csv_with_detected_columns(tmp_path):
    path = tmp_path / "k.csv"
    path.write_text("Firma;NIP;Rachunek\nA;526-025-02-74;\nB;;\n", encoding="utf-8")
    rows = read_rows(path)
    assert [(r.nip, r.account) for r in rows] == [("526-025-02-74", "")]


def test_reads_xlsx(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    wb.active.append(["Kontrahent", "NIP kontrahenta"])
    wb.active.append(["A", 5260250274])
    path = tmp_path / "k.xlsx"
    wb.save(path)
    assert read_rows(path)[0].nip == "5260250274"


def _results_table(wb):
    rows = list(wb["Wyniki"].iter_rows(min_row=4, values_only=True))
    header = rows[0]
    return header, [dict(zip(header, r, strict=True)) for r in rows[1:]]


def test_demo_run_writes_report(tmp_path, capsys):
    out = tmp_path / "raport.xlsx"
    code = main(["examples/kontrahenci.csv", "--demo", "-o", str(out), "--data", "2026-10-20"])
    assert code == 0
    wb = load_workbook(out)
    assert wb.sheetnames == ["Podsumowanie", "Wyniki", "Rachunki"]
    header, rows = _results_table(wb)
    assert header[:5] == ("Lp.", "Kontrahent (nazwa z wykazu)", "NIP", "Ocena", "Status VAT")
    statuses = [r["Status VAT"] for r in rows]
    assert statuses.count("Czynny") == 5
    assert "Błędny NIP" in statuses
    verdicts = {r["NIP"]: r["Ocena"] for r in rows}
    assert verdicts["0004182736"] == "OK"
    assert verdicts["0006391823"] == "Problem"  # account not on the list
    assert verdicts["0007419363"] == "Do weryfikacji"  # virtual accounts
    assert rows[0]["Data rejestracji"].date().isoformat() == "2015-03-02"  # real date cell
    assert rows[0]["Rachunek z pliku"] == "60 1020 1026 0000 0422 7020 1111"
    assert "Raport:" in capsys.readouterr().out


def test_summary_sheet_counts(tmp_path):
    out = tmp_path / "raport.xlsx"
    main(["examples/kontrahenci.csv", "--demo", "-o", str(out)])
    ws = load_workbook(out)["Podsumowanie"]
    assert ws["B1"].value == "Weryfikacja kontrahentów na białej liście VAT"
    tiles = {ws.cell(6, c).value: ws.cell(5, c).value for c in (2, 4, 6, 8)}
    assert tiles == {"Kontrahentów": 9, "OK": 3, "Do weryfikacji": 1, "Problem": 5}


def test_demo_run_csv_output(tmp_path):
    out = tmp_path / "raport.csv"
    assert main(["examples/kontrahenci.csv", "--demo", "-o", str(out)]) == 0
    text = out.read_text(encoding="utf-8-sig")
    assert text.startswith("Kontrahent (nazwa z wykazu);NIP;Ocena;Status VAT")
    assert "2015-03-02" in text


def test_accounts_go_to_separate_sheet(tmp_path):
    out = tmp_path / "raport.xlsx"
    main(["examples/kontrahenci.csv", "--demo", "-o", str(out)])
    wb = load_workbook(out)
    _, rows = _results_table(wb)
    assert rows[0]["Rachunków w wykazie"] == 1
    accounts = list(wb["Rachunki"].iter_rows(min_row=5, values_only=True))
    # duplicate NIP in the input file is listed once
    assert [a[2] for a in accounts].count("0004182736") == 1
    assert (
        "HURTOWNIA ALFA SP. Z O.O. (DEMO)",
        "0004182736",
        "60 1020 1026 0000 0422 7020 1111",
    ) in [a[1:] for a in accounts]


def test_empty_columns_are_left_out(tmp_path):
    src = tmp_path / "k.csv"
    src.write_text("NIP\n0004182736\n", encoding="utf-8")
    out = tmp_path / "raport.xlsx"
    main([str(src), "--demo", "-o", str(out)])
    header, _ = _results_table(load_workbook(out))
    assert "Rachunek z pliku" not in header and "NIP w pliku" not in header
