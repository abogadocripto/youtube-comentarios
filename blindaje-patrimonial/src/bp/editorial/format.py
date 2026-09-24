"""Formato numérico y de fechas es-ES (única pieza que convierte valores en texto; docs/06 §3).

Convenciones:
- miles con punto y decimales con coma: 101.250 · 1,92
- signo menos tipográfico «−» (U+2212) y signo «+» explícito en variaciones
- espacio fino no separable (U+202F) antes de % y de €
- USD con «$» delante: $101.250 · $420 M · $84 mm · $6,7 bill.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

MINUS = "−"
THIN = " "

MONTHS_SHORT = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
MONTHS_LONG = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
               "octubre", "noviembre", "diciembre"]
WEEKDAYS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _round(x: float, decimals: int) -> Decimal:
    q = Decimal(1).scaleb(-decimals) if decimals > 0 else Decimal(1)
    return Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP)


def number(x: float, decimals: int = 0, signed: bool = False) -> str:
    """Número en formato es-ES. signed=True añade «+» a los positivos (el cero no lleva signo)."""
    d = _round(x, decimals)
    neg = d < 0
    d = abs(d)
    s = f"{d:,.{decimals}f}"                 # 101,250.50 (formato en)
    s = s.replace(",", "\u0001").replace(".", ",").replace("\u0001", ".")
    # regla RAE: los números de 4 cifras no llevan separador de miles (1250), salvo en tablas;
    # por homogeneidad en cifras financieras se mantiene el separador siempre a partir de 10.000
    int_part = s.split(",")[0]
    if len(int_part.replace(".", "")) == 4:
        s = s.replace(".", "", 1)
    if neg and d != 0:
        return MINUS + s
    if signed and d != 0:
        return "+" + s
    return s


def abs_number(x: float, decimals: int = 0) -> str:
    return number(abs(x), decimals)


def pct(x: float, decimals: int = 1, signed: bool = False) -> str:
    return f"{number(x, decimals, signed)}{THIN}%"


def usd(x: float, decimals: int = 0, signed: bool = False) -> str:
    """$101.250 · −$420 (el signo precede al símbolo)."""
    body = number(abs(x), decimals)
    sign = MINUS if x < 0 and _round(x, decimals) != 0 else ("+" if signed and _round(x, decimals) != 0 else "")
    return f"{sign}${body}"


def usd_scaled(x: float, signed: bool = False) -> str:
    """Importes grandes: $420 M · $84 mm · $6,7 bill. (M = millones; mm = miles de millones; bill. = billones)."""
    ax = abs(x)
    if ax >= 1e12:
        body, suffix = number(ax / 1e12, 1), " bill."
    elif ax >= 1e9:
        body, suffix = number(ax / 1e9, 1 if ax < 1e11 else 0), " mm"
    elif ax >= 1e6:
        body, suffix = number(ax / 1e6, 1 if ax < 1e7 else 0), " M"
    else:
        body, suffix = number(ax, 0), ""
    zero = body.strip("0,.") == ""
    sign = MINUS if x < 0 and not zero else ("+" if signed and x > 0 and not zero else "")
    return f"{sign}${body}{suffix}"


def eur(x: float, decimals: int = 0, signed: bool = False) -> str:
    return f"{number(x, decimals, signed)}{THIN}€"


def btc(x: float, signed: bool = False) -> str:
    return f"{number(x, 0, signed)}{THIN}BTC"


def bp(x: float, signed: bool = True) -> str:
    return f"{number(x, 0, signed)}{THIN}pb"


def date_short(d: date | datetime) -> str:
    """6 oct 2025"""
    return f"{d.day} {MONTHS_SHORT[d.month - 1]} {d.year}"


def date_weekday(d: date | datetime) -> str:
    """Miércoles, 23 sep 2026"""
    return f"{WEEKDAYS[d.weekday()].capitalize()}, {date_short(d)}"


def month_year(d: date | datetime, approx: bool = True) -> str:
    """~abril 2028"""
    return f"{'~' if approx else ''}{MONTHS_LONG[d.month - 1]} {d.year}"


def session_label(d: date) -> str:
    """sesión del martes 22 sep"""
    return f"sesión del {WEEKDAYS[d.weekday()]} {d.day} {MONTHS_SHORT[d.month - 1]}"


def ordinal_fem(n: int) -> str:
    """3.ª"""
    return f"{n}.ª"


def fmt_value(value: Any, fmt: str, signed_override: bool | None = None) -> str:
    """Aplica un código de formato de metrics.yaml a un valor. Devuelve el texto «display»."""
    if value is None:
        return "—"
    if fmt == "text":
        return str(value)
    if fmt in ("date_short", "month_year"):
        d = value if isinstance(value, (date, datetime)) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return date_short(d) if fmt == "date_short" else month_year(d)
    x = float(value)
    s = signed_override
    table = {
        "usd_int": lambda: usd(x, 0, signed=bool(s)),
        "usd_4dp": lambda: usd(x, 4, signed=bool(s)),
        "usd_millions": lambda: usd_scaled(x, signed=True if s is None else s),
        "usd_billions": lambda: usd_scaled(x, signed=bool(s)),
        "usd_trillions": lambda: usd_scaled(x, signed=bool(s)),
        "eur_int": lambda: eur(x, 0, signed=bool(s)),
        "pct_signed_1dp": lambda: pct(x, 1, signed=True if s is None else s),
        "pct_signed_3dp": lambda: pct(x, 3, signed=True if s is None else s),
        "pct_1dp": lambda: pct(x, 1, signed=bool(s)),
        "pp_signed": lambda: f"{number(x, 1, True if s is None else s)}{THIN}pp",
        "bp_signed": lambda: bp(x, True if s is None else s),
        "int": lambda: number(x, 0, signed=bool(s)),
        "int_signed": lambda: number(x, 0, signed=True if s is None else s),
        "btc_int": lambda: btc(x, signed=bool(s)),
        "btc_signed_int": lambda: btc(x, signed=True if s is None else s),
        "ratio_1dp": lambda: number(x, 1),
        "ratio_2dp": lambda: number(x, 2),
        "ratio_3dp": lambda: number(x, 3),
        "ratio_4dp": lambda: number(x, 4),
    }
    if fmt not in table:
        raise ValueError(f"Formato desconocido: {fmt}")
    return table[fmt]()


def fmt_abs(value: Any, fmt: str) -> str | None:
    """Valor absoluto sin signo (para el marcador {{fa:…}}). None si no es numérico."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    return fmt_value(abs(float(value)), fmt, signed_override=False)
