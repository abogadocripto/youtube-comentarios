"""Estadísticos comunes (docs/04 §2). Funciones puras sobre listas ordenadas de más antigua a más reciente."""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import mean, median, pstdev


def chg_abs(xs: Sequence[float], k: int) -> float | None:
    if len(xs) <= k:
        return None
    return xs[-1] - xs[-1 - k]


def chg_pct(xs: Sequence[float], k: int) -> float | None:
    if len(xs) <= k or xs[-1 - k] == 0:
        return None
    return (xs[-1] / xs[-1 - k] - 1.0) * 100.0


def zscore(xs: Sequence[float], window: int, min_hist: int = 60) -> float | None:
    """z del último valor frente a la ventana anterior (excluye el propio valor)."""
    hist = list(xs[-window - 1:-1])
    if len(hist) < min_hist:
        return None
    sd = pstdev(hist)
    if sd == 0:
        return 0.0
    return (xs[-1] - mean(hist)) / sd


def robust_z(xs: Sequence[float], window: int, min_hist: int = 60) -> float | None:
    """(x − mediana) / (1,4826·MAD) sobre la ventana anterior; resistente a colas gordas."""
    hist = list(xs[-window - 1:-1])
    if len(hist) < min_hist:
        return None
    med = median(hist)
    mad = median(abs(v - med) for v in hist)
    if mad == 0:
        return 0.0
    return (xs[-1] - med) / (1.4826 * mad)


def pctl(xs: Sequence[float], window: int, min_hist: int = 90, value: float | None = None) -> float | None:
    """Proporción de observaciones de la ventana (incluido el último valor) que son ≤ value (por defecto, el último)."""
    win = list(xs[-window:])
    if len(win) < min_hist:
        return None
    v = win[-1] if value is None else value
    return sum(1 for x in win if x <= v) / len(win)


def pctl_of(values: Sequence[float], q: float) -> float | None:
    """Cuantil q (0–1) por interpolación lineal."""
    if not values:
        return None
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return s[lo]
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def streak(xs: Sequence[float]) -> int:
    """Número de observaciones consecutivas con el mismo signo que la última, con signo (+3, −2). 0 si la última es 0."""
    if not xs or xs[-1] == 0:
        return 0
    sign = 1 if xs[-1] > 0 else -1
    n = 0
    for v in reversed(xs):
        if (v > 0 and sign > 0) or (v < 0 and sign < 0):
            n += 1
        else:
            break
    return n * sign


def n_day_extreme(xs: Sequence[float], n: int) -> str | None:
    """'max' si el último valor es el máximo de las últimas n observaciones, 'min' si es el mínimo."""
    win = list(xs[-n:])
    if len(win) < n:
        return None
    if xs[-1] >= max(win):
        return "max"
    if xs[-1] <= min(win):
        return "min"
    return None


def biggest_since(xs: Sequence[float], min_lookback: int, absolute: bool = True) -> int | None:
    """Devuelve cuántas observaciones atrás hubo un valor mayor o igual (en |x| si absolute y mismo signo),
    si ese número es ≥ min_lookback. None si no es extremo en esa ventana."""
    if len(xs) < 2:
        return None
    last = xs[-1]
    for i in range(len(xs) - 2, -1, -1):
        prev = xs[i]
        cmp_prev = abs(prev) if absolute else prev
        cmp_last = abs(last) if absolute else last
        same_sign = (prev > 0) == (last > 0)
        if cmp_prev >= cmp_last and (same_sign or not absolute):
            back = len(xs) - 1 - i
            return back if back >= min_lookback else None
    back = len(xs) - 1
    return back if back >= min_lookback else None


def crossed(prev: float | None, cur: float | None, level: float) -> str | None:
    """'up' si cruza el nivel al alza, 'down' si a la baja."""
    if prev is None or cur is None:
        return None
    if prev < level <= cur:
        return "up"
    if prev > level >= cur:
        return "down"
    return None


def log_returns(prices: Sequence[float]) -> list[float]:
    return [math.log(b / a) for a, b in zip(prices, prices[1:], strict=False) if a > 0 and b > 0]


def realized_vol_daily(prices: Sequence[float], window: int = 30) -> float | None:
    """Desviación típica de los rendimientos logarítmicos diarios (fracción, no %)."""
    rets = log_returns(prices[-window - 1:])
    if len(rets) < min(window, 20):
        return None
    return pstdev(rets)


def sigma_move(chg_24h_pct: float | None, vol_daily: float | None) -> float | None:
    if chg_24h_pct is None or not vol_daily:
        return None
    return (chg_24h_pct / 100.0) / vol_daily


def hysteresis(prev_state: str | None, raw_state: str, raw_history: Sequence[str], confirmations: int) -> str:
    """El estado solo cambia si raw_state se repite `confirmations` lecturas seguidas (incluida la actual)."""
    if prev_state is None or raw_state == prev_state:
        return raw_state
    recent = list(raw_history[-(confirmations - 1):]) + [raw_state] if confirmations > 1 else [raw_state]
    if len(recent) >= confirmations and all(s == raw_state for s in recent):
        return raw_state
    return prev_state
