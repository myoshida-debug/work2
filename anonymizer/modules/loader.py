from pathlib import Path
from .utils import load_yaml


def load_config(config_dir: Path):
    return load_yaml(config_dir / 'columns.yml')
