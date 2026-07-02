from __future__ import annotations

import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

PROMPT_DIR = Path(__file__).resolve().parent
_ENV = Environment(
    loader=FileSystemLoader(PROMPT_DIR),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)
_ENV.filters["tojson"] = lambda value: json.dumps(value, ensure_ascii=False)


def render_prompt(template_name: str, **context) -> str:
    return _ENV.get_template(template_name).render(**context)
