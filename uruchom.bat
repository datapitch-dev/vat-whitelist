@echo off
rem Przeciagnij plik CSV/XLSX na ten plik albo uruchom bez argumentu, zeby zobaczyc demo.
cd /d "%~dp0"
python -m pip install -q -e . || goto :error
if "%~1"=="" (
    python -m vat_whitelist examples\kontrahenci.csv --demo -o raport_demo.xlsx
) else (
    python -m vat_whitelist "%~1"
)
pause
exit /b 0
:error
echo Nie udalo sie zainstalowac. Sprawdz, czy masz Pythona 3.10+.
pause
exit /b 1
