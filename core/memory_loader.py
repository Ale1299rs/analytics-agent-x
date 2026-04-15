from pathlib import Path
from typing import Any, Dict, List

import yaml

from .config import MEMORY_PATH
from .utils import safe_load_yaml, safe_read_text


class MemoryLoader:
    def __init__(self, base_path: Path = MEMORY_PATH):
        self.base_path = base_path

    def list_cookbooks(self) -> List[str]:
        cookbooks_dir = self.base_path / "cookbooks"
        if not cookbooks_dir.exists():
            return ["default"]
        return sorted([p.name for p in cookbooks_dir.iterdir() if p.is_dir()])

    def load_cookbook(self, cookbook_name: str = "default") -> Dict[str, Any]:
        cookbook_path = self.base_path / "cookbooks" / cookbook_name
        ingredients_raw = safe_load_yaml(cookbook_path / "ingredients.yaml")
        recipes_raw = safe_load_yaml(cookbook_path / "recipes.yaml")
        rules = safe_read_text(cookbook_path / "rules.md")
        examples = safe_read_text(cookbook_path / "examples.sql")

        # ingredients.yaml can be a list or a dict with key "ingredients"
        if isinstance(ingredients_raw, list):
            ingredients = ingredients_raw
        else:
            ingredients = ingredients_raw.get("ingredients", []) if ingredients_raw else []

        if isinstance(recipes_raw, list):
            recipes = recipes_raw
        else:
            recipes = recipes_raw.get("recipes", []) if recipes_raw else []

        return {
            "name": cookbook_name,
            "ingredients": ingredients,
            "recipes": recipes,
            "rules": rules,
            "examples": examples,
        }

    def load_learned_patterns(self) -> Dict[str, Any]:
        return safe_load_yaml(self.base_path / "learned_patterns.yaml")

    def save_learned_patterns(self, patterns: Dict[str, Any]) -> None:
        path = self.base_path / "learned_patterns.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(patterns, f, sort_keys=False, allow_unicode=True)
