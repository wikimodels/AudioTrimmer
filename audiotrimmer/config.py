"""Shared app settings (source / output folders), stored in config.json."""

import json
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

DEFAULTS = {
    "source": r"C:\Users\Vitali\Downloads\YandexMusic",
    "output": r"C:\Users\Vitali\Downloads\TrimmedAudio",
}


def load() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            pass
    return cfg


def save(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")