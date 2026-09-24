from datetime import date

import pytest

from bp.editorial import format as F

M, T = F.MINUS, F.THIN


@pytest.mark.parametrize(("x", "dec", "signed", "expected"), [
    (101250, 0, False, "101.250"),
    (1250, 0, False, "1250"),                 # RAE: 4 cifras sin separador
    (-1250.5, 1, False, f"{M}1250,5"),
    (0.3, 1, True, "+0,3"),
    (0, 1, True, "0,0"),                      # el cero no lleva signo
    (-0.04, 1, True, "0,0"),                  # redondea a cero: sin signo menos
    (2.45, 1, False, "2,5"),                  # redondeo comercial, no bancario
    (1234567.891, 2, False, "1.234.567,89"),
])
def test_number(x, dec, signed, expected):
    assert F.number(x, dec, signed) == expected


def test_currency_and_units():
    assert F.usd(101250) == "$101.250"
    assert F.usd(-420, signed=True) == f"{M}$420"
    assert F.usd_scaled(-420e6) == f"{M}$420 M"
    assert F.usd_scaled(84.2e9) == "$84,2 mm"
    assert F.usd_scaled(6.74e12) == "$6,7 bill."
    assert F.eur(86540) == f"86.540{T}€"
    assert F.pct(-2.4, signed=True) == f"{M}2,4{T}%"
    assert F.bp(-12) == f"{M}12{T}pb"


def test_fmt_value_and_abs():
    assert F.fmt_value(-19.69, "pct_signed_1dp") == f"{M}19,7{T}%"
    assert F.fmt_abs(-19.69, "pct_signed_1dp") == f"19,7{T}%"
    assert F.fmt_abs("expansion", "text") is None
    assert F.fmt_value(None, "int") == "—"
    with pytest.raises(ValueError):
        F.fmt_value(1, "desconocido")


def test_dates():
    assert F.date_short(date(2025, 10, 6)) == "6 oct 2025"
    assert F.date_weekday(date(2026, 9, 24)) == "Jueves, 24 sep 2026"
    assert F.session_label(date(2026, 9, 22)) == "sesión del martes 22 sep"
    assert F.month_year(date(2028, 4, 1)) == "~abril 2028"
    assert F.month_year(date(2026, 8, 31), approx=False) == "agosto 2026"
