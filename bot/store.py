from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict


def load_mapping(path: str) -> Dict[str, int]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        out: Dict[str, int] = {}
        for k, v in data.items():
            try:
                out[k] = int(v)
            except Exception:
                continue
        return out
    except Exception:
        return {}


def save_mapping(path: str, mapping: Dict[str, int]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(prefix="mapping_", suffix=".json", dir=str(p.parent))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, p)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass