from pathlib import Path

import app.config as config
from app.config import Settings


def test_relative_data_dir_uses_exe_dir_in_frozen_build(monkeypatch, tmp_path):
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.setattr(config, "_IS_FROZEN", True)

    exe = tmp_path / "OpenTDXStockPanel.exe"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setattr(config.sys, "executable", str(exe))

    settings = Settings(data_dir=Path("portable-data"))

    assert settings.data_dir == tmp_path / "portable-data"
