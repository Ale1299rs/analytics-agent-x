import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

import yaml


def safe_load_yaml(path: Path) -> Any:
    """Load YAML file, return empty dict if missing or invalid."""
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except (yaml.YAMLError, OSError):
        return {}


def safe_read_text(path: Path) -> str:
    """Read text file, return empty string if missing."""
    if not path.exists():
        return ""
    try:
        with path.open("r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def append_jsonl(path: Path, record: dict) -> None:
    """Append a JSON record to a JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def timestamp_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_json_text(text: str) -> Any:
    """Extract JSON from LLM response, handling markdown code blocks.

    Returns dict, list, or {} on failure.
    """
    if not text or not text.strip():
        return {}

    cleaned = text.strip()

    # Try direct parse first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strip markdown code blocks: ```json ... ``` or ``` ... ```
    md_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", cleaned, re.DOTALL)
    if md_match:
        try:
            return json.loads(md_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try to find first { ... } block
    brace_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # Try to find first [ ... ] block (for array responses like follow-ups)
    bracket_match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if bracket_match:
        try:
            return json.loads(bracket_match.group(0))
        except json.JSONDecodeError:
            pass

    return {}


def truncate_rows_for_prompt(rows: List[dict], max_rows: int = 20) -> str:
    """Format result rows as a readable string for LLM prompts."""
    if not rows:
        return "(nessun risultato)"
    preview = rows[:max_rows]
    lines = []
    if preview:
        headers = list(preview[0].keys())
        lines.append(" | ".join(headers))
        lines.append("-" * len(lines[0]))
        for row in preview:
            lines.append(" | ".join(str(row.get(h, "")) for h in headers))
    if len(rows) > max_rows:
        lines.append(f"... ({len(rows) - max_rows} righe aggiuntive omesse)")
    return "\n".join(lines)


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for mixed Italian/English."""
    return max(1, len(text) // 4)
