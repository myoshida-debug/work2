def load_default_template() -> str:
    from .prompt_template_store import load_default_template as load_from_txt

    return load_from_txt()
