"""Golden: el ejemplo renderizado versionado coincide byte a byte con la salida del renderizador.

Si un cambio de plantilla o de formato es intencionado, regenerar el ejemplo:
    python -c "import sys; sys.path.insert(0,'tests'); from test_golden import regenerate; regenerate()"
"""

from __future__ import annotations

from bp.config import load_config
from bp.llm.models import DailyOutput
from helpers import cfg_licensed, golden_input, golden_output, render

GOLDEN = load_config().root / "schema" / "examples" / "daily_rendered.example.html"


def _render() -> str:
    return render(cfg_licensed(), golden_input(), DailyOutput.model_validate(golden_output())).html + "\n"


def regenerate() -> None:
    GOLDEN.write_text(_render(), "utf-8")


def test_rendered_example_matches_renderer():
    assert GOLDEN.read_text("utf-8") == _render()
