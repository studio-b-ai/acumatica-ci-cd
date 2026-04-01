"""
Pattern Catalog — persistent state for threshold-based generation.

Tracks observed workflow patterns and their counts. When a pattern's
count crosses the threshold, it signals that a SOP and/or test case
should be generated.
"""

from __future__ import annotations

import json
import os
from typing import Optional

from .models import PatternEntry, WorkflowPath
from .grouper import signature_hash


class PatternCatalog:
    """Persistent catalog of observed workflow patterns."""

    def __init__(
        self,
        path: str = "workflow_patterns.json",
        threshold: int = 3,
    ):
        self.path = path
        self.threshold = threshold
        self.last_fetched: Optional[str] = None
        self.patterns: dict[str, PatternEntry] = {}
        self._load()

    def _load(self) -> None:
        """Load catalog from disk if it exists."""
        if not os.path.exists(self.path):
            return
        with open(self.path, "r") as f:
            data = json.load(f)
        self.last_fetched = data.get("last_fetched")
        self.threshold = data.get("threshold", self.threshold)
        for key, entry_data in data.get("patterns", {}).items():
            self.patterns[key] = PatternEntry.from_dict(entry_data)

    def save(self) -> None:
        """Persist catalog to disk."""
        data = {
            "last_fetched": self.last_fetched,
            "threshold": self.threshold,
            "patterns": {
                key: entry.to_dict()
                for key, entry in self.patterns.items()
            },
        }
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    def update(
        self,
        pattern_groups: dict[str, list[WorkflowPath]],
    ) -> list[PatternEntry]:
        """Merge new observations into the catalog.

        Args:
            pattern_groups: Output from grouper.detect_patterns()

        Returns:
            List of PatternEntries that just crossed the threshold
            (i.e., need SOP/test generation for the first time).
        """
        newly_crossed = []

        for sig_hash, paths in pattern_groups.items():
            if sig_hash not in self.patterns:
                # New pattern — create entry from first path
                first_path = paths[0]
                # Extract step signatures from the first path's operations
                step_sigs = []
                for op in first_path.operations:
                    if op.signature not in step_sigs:
                        step_sigs.append(op.signature)

                self.patterns[sig_hash] = PatternEntry(
                    signature=first_path.signature,
                    step_signatures=step_sigs,
                    screen_id=first_path.screen_id,
                )

            entry = self.patterns[sig_hash]
            was_below = not entry.above_threshold(self.threshold)

            for path in paths:
                entry.add_observation(path)

            now_above = entry.above_threshold(self.threshold)
            if was_below and now_above:
                newly_crossed.append(entry)

        return newly_crossed

    def patterns_above_threshold(self) -> list[PatternEntry]:
        """Return all patterns at or above the threshold."""
        return [
            entry for entry in self.patterns.values()
            if entry.above_threshold(self.threshold)
        ]

    def patterns_needing_generation(self) -> list[PatternEntry]:
        """Return patterns above threshold that don't have SOPs/tests yet."""
        return [
            entry for entry in self.patterns.values()
            if entry.above_threshold(self.threshold)
            and (entry.sop_generated is None or entry.test_generated is None)
        ]

    def summary(self) -> dict:
        """Summary stats for display."""
        total = len(self.patterns)
        above = len(self.patterns_above_threshold())
        needing = len(self.patterns_needing_generation())
        return {
            "total_patterns": total,
            "above_threshold": above,
            "needing_generation": needing,
            "threshold": self.threshold,
            "last_fetched": self.last_fetched,
        }
