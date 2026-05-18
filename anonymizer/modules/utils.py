import json
import re
from pathlib import Path
import yaml


def load_yaml(path: Path):
    with path.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def write_json(path: Path, value):
    with path.open('w', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def load_json(path: Path):
    with path.open('r', encoding='utf-8') as f:
        return json.load(f)


def normalize_label(label: str) -> str:
    return re.sub(r'\s+', '_', label.strip())
