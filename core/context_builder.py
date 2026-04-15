from typing import Any, Dict, List

from .cost_guard import CostGuard
from .memory_loader import MemoryLoader


class ContextBuilder:
    """Selects the minimum relevant context for a question."""

    def __init__(self, memory_loader: MemoryLoader, cost_guard: CostGuard):
        self.memory_loader = memory_loader
        self.cost_guard = cost_guard

    def build(self, question: str, cookbook_name: str = "default") -> Dict[str, Any]:
        cookbook = self.memory_loader.load_cookbook(cookbook_name)
        learned = self.memory_loader.load_learned_patterns()
        self.cost_guard.register_prompt(question)

        question_lower = question.lower()
        tokens = set(self._tokenize(question_lower))

        # Select relevant ingredients by matching question tokens against
        # name, description, and example_questions
        selected_ingredients = self._match_ingredients(
            cookbook.get("ingredients", []), tokens, question_lower
        )

        # Select relevant recipes by matching triggers
        selected_recipes = self._match_recipes(
            cookbook.get("recipes", []), tokens, question_lower
        )

        # Select relevant learned patterns
        patterns = self._match_patterns(
            learned.get("patterns", []), tokens, question_lower
        )

        # Build formatted table schema for LLM prompts
        table_schemas = self._format_table_schemas(selected_ingredients)

        return {
            "cookbook_name": cookbook_name,
            "ingredients": selected_ingredients,
            "recipes": selected_recipes,
            "rules": cookbook.get("rules", ""),
            "examples": cookbook.get("examples", ""),
            "learned_patterns": patterns,
            "table_schemas": table_schemas,
        }

    def _tokenize(self, text: str) -> List[str]:
        """Split text into meaningful tokens (length > 2)."""
        return [w for w in text.split() if len(w) > 2]

    def _match_ingredients(
        self, ingredients: List[dict], tokens: set, question_lower: str
    ) -> List[dict]:
        scored = []
        for ing in ingredients:
            score = 0
            name = ing.get("name", "").lower()
            desc = ing.get("description", "").lower()
            examples = " ".join(ing.get("example_questions", [])).lower()
            searchable = f"{name} {desc} {examples}"

            # Direct name match is strong signal
            if name and name.replace("_", " ").split()[-1] in question_lower:
                score += 5

            # Token overlap
            for token in tokens:
                if token in searchable:
                    score += 1

            if score > 0:
                scored.append((score, ing))

        scored.sort(key=lambda x: x[0], reverse=True)
        if scored:
            return [item[1] for item in scored]

        # Fallback: return all ingredients (context is small for demo)
        return ingredients[:4]

    def _match_recipes(
        self, recipes: List[dict], tokens: set, question_lower: str
    ) -> List[dict]:
        matched = []
        for recipe in recipes:
            triggers = recipe.get("triggers", [])
            # Match if any trigger appears in the question
            if any(trigger.lower() in question_lower for trigger in triggers):
                matched.append(recipe)

        return matched if matched else recipes[:2]

    def _match_patterns(
        self, patterns: List[dict], tokens: set, question_lower: str
    ) -> List[dict]:
        matched = []
        for pattern in patterns:
            q_pattern = pattern.get("question_pattern", "").lower()
            if any(token in q_pattern for token in tokens):
                matched.append(pattern)
        return matched

    def _format_table_schemas(self, ingredients: List[dict]) -> str:
        """Format ingredient metadata into a readable schema for LLM prompts."""
        if not ingredients:
            return "(nessuno schema disponibile)"

        lines = []
        for ing in ingredients:
            name = ing.get("name", "unknown")
            lines.append(f"## {name}")
            if ing.get("description"):
                lines.append(f"Descrizione: {ing['description']}")
            if ing.get("grain"):
                lines.append(f"Granularità: {ing['grain']}")
            if ing.get("date_column"):
                lines.append(f"Colonna data: {ing['date_column']}")
            if ing.get("columns"):
                lines.append(f"Colonne: {', '.join(ing['columns'])}")
            if ing.get("joins"):
                joins_str = "; ".join(
                    f"{j['table']} via {j['key']}" for j in ing["joins"]
                )
                lines.append(f"Join: {joins_str}")
            if ing.get("required_filters"):
                lines.append(f"Filtri obbligatori: {', '.join(ing['required_filters'])}")
            if ing.get("preferred_dimensions"):
                lines.append(f"Dimensioni preferite: {', '.join(ing['preferred_dimensions'])}")
            lines.append("")

        return "\n".join(lines)
