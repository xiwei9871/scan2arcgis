"""Regression checks for repository-relocatable OCR runtime configuration."""
import json
from pathlib import Path

from tools.stitchvector_studio import registry

ROOT = Path(__file__).resolve().parents[2]
PLUGINS = ROOT / "tools/stitchvector_studio/plugins"


def test_ocr_python_manifests_use_repo_relative_paths():
    expected = {
        "rapidocr": ".venv-ocr/bin/python",
        "paddleocr": "runs/ocr_poc01/venvs/paddle/bin/python",
    }
    for name, relative in expected.items():
        m = json.loads((PLUGINS / name / "manifest.json").read_text(encoding="utf-8"))
        assert m["runtime"]["python"] == relative
        assert registry.resolve_python(m["runtime"]) == str(ROOT / relative)


def test_studio_runtime_uses_current_interpreter():
    import sys
    assert registry.resolve_python({"python": "studio"}) == sys.executable


def test_paddle_cache_defaults_to_repository(monkeypatch):
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    import importlib
    from tools.stitchvector_studio.plugins.paddleocr import plugin
    importlib.reload(plugin)
    assert plugin.CACHE == ROOT / "runs/ocr_poc01/cache/paddle"
