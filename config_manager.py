"""Impostazioni locali dell'interfaccia, salvate in %APPDATA%\\SmartCFO\\config.json.

La chiave API non è mai salvata qui: viene letta dalla variabile d'ambiente
(vedi ai_config.API_KEY_ENV). Eventuali altri campi già presenti nel file
vengono conservati invariati.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "SmartCFO"
CONFIG_PATH = APP_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "appearance": "dark",
    "last_dir": str(Path.home()),
}


class ConfigManager:
    def __init__(self, path: Path = CONFIG_PATH):
        self.path = path
        self.data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            stored = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(stored, dict):
                self.data.update(stored)
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            # Config corrotta: si riparte dai default senza perdere il file originale.
            try:
                self.path.replace(self.path.with_suffix(".json.bak"))
            except OSError:
                pass

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
        if sys.platform != "win32":
            os.chmod(self.path, 0o600)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value
        self.save()
