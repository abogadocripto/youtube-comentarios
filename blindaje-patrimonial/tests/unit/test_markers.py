import pytest

from bp.editorial.markers import MarkerError, fill, markers_in

FACTS = {"etf": {"id": "etf", "display": "−$420 M", "display_abs": "$420 M"},
         "fng": {"id": "fng", "display": "58", "display_abs": "58"},
         "txt": {"id": "txt", "display": "expansión", "display_abs": None}}
HINTS = {"fng:h.path": "de {{f:fng}} <b>hoy</b>", "loop": "{{h:loop}}"}


def test_fill_signed_and_abs():
    assert fill("Salidas de {{fa:etf}} ({{f:etf}})", FACTS, HINTS) == "Salidas de $420 M (−$420 M)"


def test_fill_hint_recursive_and_escape():
    assert fill("El índice pasa {{h:fng:h.path}}", FACTS, HINTS, escape=True) == "El índice pasa de 58 &lt;b&gt;hoy&lt;/b&gt;"


def test_unknown_marker_raises():
    with pytest.raises(MarkerError):
        fill("{{f:nope}}", FACTS, HINTS)
    with pytest.raises(MarkerError):
        fill("{{fa:txt}}", FACTS, HINTS)      # un valor de texto no admite {{fa:}}


def test_recursion_is_bounded():
    with pytest.raises(MarkerError):
        fill("{{h:loop}}", FACTS, HINTS)


def test_markers_in():
    assert markers_in("a {{f:x}} b {{h:y:h.z}}") == [("f", "x"), ("h", "y:h.z")]
