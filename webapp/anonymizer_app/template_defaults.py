from pathlib import Path


def load_default_template() -> str:
    default_path = Path(__file__).resolve().parent / 'prompt_templates' / 'default.txt'
    if default_path.exists():
        return default_path.read_text(encoding='utf-8')
    return ''
