from pathlib import Path
from .utils import write_json


def write_restore_metadata(path: Path, source_id: str, restore_map: dict):
    payload = {
        'source_id': source_id,
        'restore_map': restore_map,
    }
    write_json(path, payload)


def write_prompt_file(path: Path, payload: dict):
    write_json(path, payload)


def write_result_file(path: Path, payload: dict):
    write_json(path, payload)
