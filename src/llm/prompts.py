from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel

_PROMPTS_PATH = Path(__file__).parent / "prompts.yaml"


class PromptSpec(BaseModel):
    description: str | None = None
    template: str


class PromptLibrary:
    def __init__(self, path: Path = _PROMPTS_PATH) -> None:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.system: str = (data.get("system") or "").strip()
        self._specs: dict[str, PromptSpec] = {
            name: PromptSpec(**body)
            for name, body in (data.get("prompts") or {}).items()
        }
        self._jinja_env = Environment(
            undefined=StrictUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=False,
        )

    def render(self, name: str, **variables: Any) -> str:
        """Render the named prompt with the given variables."""
        spec = self._specs.get(name)
        if spec is None:
            raise KeyError(f"Unknown prompt: {name!r}")
        return self._jinja_env.from_string(spec.template).render(**variables).strip()


def get_prompts() -> PromptLibrary:
    """Return a fresh prompt library (reads `prompts.yaml` from disk)."""
    return PromptLibrary()
