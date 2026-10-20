# vat-whitelist

Hurtowe sprawdzanie kontrahentów na **białej liście podatników VAT** (Wykaz podatników VAT
Ministerstwa Finansów) przez oficjalne, darmowe API `wl-api.mf.gov.pl`.
Na wejściu CSV albo Excel z NIP-ami, na wyjściu raport w Excelu ze statusem VAT, danymi firmy,
weryfikacją numeru rachunku i identyfikatorem zapytania, który jest dowodem sprawdzenia.

```
$ vat-whitelist kontrahenci.csv
Kontrahentów: 9, stan na 2026-10-20
  zapytanie 1/1
  Brak w wykazie: 1
  Błędny NIP: 1
  Czynny: 5
  Niezarejestrowany: 1
  Rachunek: Błędny numer: 1
  Rachunek: NIE: 1
  Rachunek: Sprawdź ręcznie: 1
  Rachunek: TAK: 1
  Zwolniony: 1
Zapytań do API: 1, z pamięci podręcznej: 0
Raport: raport_2026-10-20.xlsx
```

## Po co to

Przelew powyżej 15 000 zł na rachunek, którego nie ma na białej liście, oznacza, że wydatku nie
można zaliczyć do kosztów, a płacący może odpowiadać solidarnie za VAT sprzedawcy. Sprawdzanie
kontrahentów po jednym na stronie podatki.gov.pl przy kilkuset fakturach miesięcznie to godziny
klikania. To narzędzie robi to w jednym poleceniu i zostawia ślad w postaci raportu.

## Co robi

- **Waliduje dane przed wysłaniem.** Normalizuje NIP-y (`PL 526-025-02-74` → `5260250274`),
  sprawdza cyfrę kontrolną NIP i sumę kontrolną IBAN rachunku. Błędne numery trafiają do
  raportu jako błędne i nie zużywają zapytań.
- **Oszczędza limit API.** Usuwa duplikaty i pyta o 30 NIP-ów naraz (maksimum API).
  Oficjalna dokumentacja podaje 100 zapytań wyszukiwania na dobę, więc jedno uruchomienie
  sprawdzi do 3000 kontrahentów.
- **Pamięta, co już sprawdziło.** Wyniki trafiają do lokalnej bazy SQLite. Ponowne
  uruchomienie dla tej samej daty nie wysyła zapytań, a gdy limit skończy się w połowie listy,
  następnego dnia sprawdzane są tylko brakujące NIP-y.
- **Radzi sobie z kaprysami API.** Ponawia zapytania przy błędach sieci, błędach 5xx i kodach
  WL-195/WL-196 (aktualizacja bazy MF), z rosnącym odstępem. Przy wyczerpanym limicie zapisuje
  częściowy raport zamiast się wywracać.
- **Sprawdza rachunek bez dodatkowych zapytań.** Jeśli plik ma kolumnę z numerem rachunku,
  narzędzie porównuje go z rachunkami z wykazu. Gdy firma używa rachunków wirtualnych (których
  wykaz nie podaje w całości), wynik to „Sprawdź ręcznie”, a nie fałszywe „NIE”.
- **Raport, który da się od razu oddać.** Arkusz „Wyniki” z kolorami (zielony: w porządku,
  żółty: do uwagi, czerwony: problem), filtrami i zamrożonym nagłówkiem oraz arkusz
  „Podsumowanie”. Kolumna „Id zapytania” to identyfikator nadany przez MF, który potwierdza,
  że kontrahent był sprawdzony danego dnia.

## Instalacja i użycie

Wymaga Pythona 3.10+.

```bash
pip install -e .
vat-whitelist examples/kontrahenci.csv --demo      # demo bez internetu
vat-whitelist kontrahenci.xlsx -o raport.xlsx       # prawdziwe API, stan na dziś
vat-whitelist faktury.csv --kolumna-nip "NIP sprzedawcy" --kolumna-rachunek "Konto" --data 2026-09-30
```

Na Windowsie wystarczy przeciągnąć plik CSV lub XLSX na `uruchom.bat`. Uruchomiony bez pliku
pokaże demo.

| Opcja | Znaczenie |
| --- | --- |
| `-o, --wynik` | plik raportu `.xlsx` albo `.csv` (CSV ze średnikiem, otwiera się w polskim Excelu) |
| `--kolumna-nip` | nazwa kolumny z NIP-em; domyślnie wykrywana (`NIP`, `NIP kontrahenta`, …) |
| `--kolumna-rachunek` | kolumna z rachunkiem do weryfikacji; domyślnie wykrywana (`Rachunek`, `Konto`, `IBAN`, …) |
| `--data` | stan na dzień (RRRR-MM-DD), np. dzień zapłaty faktury |
| `--limit` | ile zapytań wysłać najwyżej na dobę (domyślnie 100) |
| `--cache` | plik bazy z wynikami (domyślnie `.vat_whitelist.sqlite`) |
| `--demo` | odpowiedzi z wbudowanych danych testowych zamiast z API |

Kod wyjścia to 0, gdy sprawdzono wszystko, 1, gdy część listy czeka na kolejne uruchomienie,
i 2 przy błędnym pliku wejściowym.

## Budowa

```
src/vat_whitelist/
  identifiers.py   normalizacja i sumy kontrolne NIP oraz rachunku
  client.py        klient API: paczki po 30, ponawianie, mapowanie kodów błędów
  cache.py         SQLite: wyniki (NIP, data) i licznik zapytań na dzień
  checker.py       logika: walidacja, duplikaty, budżet zapytań, wiersze wyników
  inputs.py        odczyt CSV (wykrywa separator) i XLSX
  report.py        raport XLSX i CSV
  demo.py          udawane API do demo i CI
  cli.py           wiersz poleceń
```

Testy (`pytest`) działają bez sieci: klient dostaje podstawioną sesję HTTP, więc da się
sprawdzić ponawianie, limit dzienny i paczkowanie bez wysyłania zapytań do MF.

```bash
pip install -e ".[dev]"
pytest
ruff check .
```

## Zastrzeżenia

Dane pochodzą z publicznego API Ministerstwa Finansów i są tak aktualne jak wykaz. Raport nie
jest poradą podatkową. NIP-y w `examples/` zaczynają się od 000 (nie ma takiego kodu urzędu
skarbowego), więc nie wskazują żadnej prawdziwej firmy.

## Licencja

MIT
