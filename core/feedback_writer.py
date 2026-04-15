import logging
from pathlib import Path
from typing import List, Optional

import yaml

from .config import MEMORY_PATH
from .models import FeedbackEntry
from .utils import append_jsonl, safe_load_yaml, timestamp_iso

logger = logging.getLogger(__name__)


class FeedbackWriter:
    def __init__(self, memory_path: Path = MEMORY_PATH):
        self.memory_path = memory_path
        self.feedback_file = self.memory_path / "user_feedback.jsonl"
        self.patterns_file = self.memory_path / "learned_patterns.yaml"

    def save_feedback(
        self,
        question: str,
        system_answer: str,
        user_feedback: str,
        corrected_sql: str = "",
        corrected_tables: Optional[List[str]] = None,
    ) -> None:
        corrected_tables = corrected_tables or []

        entry = FeedbackEntry(
            question=question,
            system_answer=system_answer,
            user_feedback=user_feedback,
            corrected_sql=corrected_sql,
            corrected_tables=corrected_tables,
            timestamp=timestamp_iso(),
        )

        append_jsonl(self.feedback_file, entry.__dict__)
        logger.info("Feedback salvato per: %s", question[:80])

        # Update learned patterns if user provided corrections
        if corrected_sql or corrected_tables:
            self._update_learned_patterns(entry)

    def _update_learned_patterns(self, feedback: FeedbackEntry) -> None:
        patterns_data = safe_load_yaml(self.patterns_file)
        pattern_list = patterns_data.get("patterns", [])

        new_pattern = {
            "question_pattern": feedback.question,
            "correct_table_choices": feedback.corrected_tables,
            "correct_filters": [],
            "known_failures": [],
            "preferred_sql_snippets": (
                [feedback.corrected_sql] if feedback.corrected_sql else []
            ),
        }
        pattern_list.append(new_pattern)
        patterns_data["patterns"] = pattern_list

        self.patterns_file.parent.mkdir(parents=True, exist_ok=True)
        with self.patterns_file.open("w", encoding="utf-8") as f:
            yaml.safe_dump(patterns_data, f, sort_keys=False, allow_unicode=True)

        logger.info("Learned pattern aggiornato da feedback utente.")
