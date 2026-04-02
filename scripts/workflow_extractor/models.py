"""
Data models for the workflow extractor.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AuditRecord:
    """Single row from StudioBAuditTrail GI."""

    batch_id: int
    change_id: int
    screen_id: str
    operation: str          # "Created", "Modified", "Deleted"
    change_date: datetime
    table_name: str
    combined_key: list[str]          # parsed from null-byte-delimited string
    modified_fields: dict[str, str]  # field_name -> value (parsed from alternating pairs)
    username: Optional[str] = None

    @property
    def step_signature(self) -> str:
        """Hashable signature for this record's role in a workflow.

        Format: ScreenID:Operation:TableName
        """
        return f"{self.screen_id}:{self.operation}:{self.table_name}"


@dataclass
class Operation:
    """A group of AuditRecords sharing the same BatchID.

    Represents one user "Save" — all the table changes Acumatica makes
    in a single persistence round.
    """

    batch_id: int
    records: list[AuditRecord]

    @property
    def screen_id(self) -> str:
        return self.records[0].screen_id if self.records else ""

    @property
    def change_date(self) -> datetime:
        return self.records[0].change_date if self.records else datetime.min

    @property
    def username(self) -> Optional[str]:
        for r in self.records:
            if r.username:
                return r.username
        return None

    @property
    def tables_affected(self) -> list[str]:
        seen = []
        for r in self.records:
            if r.table_name not in seen:
                seen.append(r.table_name)
        return seen

    @property
    def primary_operation(self) -> str:
        """The dominant operation type (Created > Modified > Deleted)."""
        ops = [r.operation for r in self.records]
        if "Created" in ops:
            return "Created"
        if "Deleted" in ops:
            return "Deleted"
        return "Modified"

    @property
    def entity_key(self) -> str:
        """The primary entity key (shortest combined_key, typically the header)."""
        if not self.records:
            return ""
        header = min(self.records, key=lambda r: len(r.combined_key))
        return "|".join(header.combined_key)

    @property
    def signature(self) -> str:
        """Unique signature for this operation's pattern.

        Sorted step signatures joined by ' -> '.
        """
        # Deduplicate while preserving order
        sigs = []
        for r in self.records:
            s = r.step_signature
            if s not in sigs:
                sigs.append(s)
        return " -> ".join(sigs)


@dataclass
class WorkflowPath:
    """An ordered sequence of Operations on the same entity.

    Represents a multi-step user workflow, e.g.:
    Create SO → Add lines → Confirm → Ship
    """

    screen_id: str
    entity_key: str
    operations: list[Operation]

    @property
    def signature(self) -> str:
        """Hashable signature for this entire workflow path."""
        return " | ".join(op.signature for op in self.operations)

    @property
    def step_count(self) -> int:
        return len(self.operations)

    @property
    def first_date(self) -> datetime:
        return self.operations[0].change_date if self.operations else datetime.min

    @property
    def last_date(self) -> datetime:
        return self.operations[-1].change_date if self.operations else datetime.min


@dataclass
class PatternEntry:
    """A recurring workflow pattern tracked in the catalog.

    When count >= threshold, SOPs and test cases are generated.
    """

    signature: str
    step_signatures: list[str]  # individual operation signatures in order
    count: int = 0
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    screen_id: str = ""
    sop_generated: Optional[str] = None
    test_generated: Optional[str] = None
    examples: list[dict] = field(default_factory=list)

    def add_observation(self, path: WorkflowPath, max_examples: int = 5) -> None:
        """Record a new observation of this pattern."""
        self.count += 1
        date_str = path.first_date.isoformat()
        if self.first_seen is None or date_str < self.first_seen:
            self.first_seen = date_str
        if self.last_seen is None or date_str > self.last_seen:
            self.last_seen = date_str
        if not self.screen_id:
            self.screen_id = path.screen_id
        if len(self.examples) < max_examples:
            self.examples.append({
                "entity_key": path.entity_key,
                "username": path.operations[0].username,
                "date": date_str,
            })

    def crossed_threshold(self, threshold: int) -> bool:
        """True if count just reached the threshold (exactly equals it)."""
        return self.count == threshold

    def above_threshold(self, threshold: int) -> bool:
        """True if count is at or above the threshold."""
        return self.count >= threshold

    def to_dict(self) -> dict:
        return {
            "signature": self.signature,
            "step_signatures": self.step_signatures,
            "count": self.count,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "screen_id": self.screen_id,
            "sop_generated": self.sop_generated,
            "test_generated": self.test_generated,
            "examples": self.examples,
        }

    @classmethod
    def from_dict(cls, data: dict) -> PatternEntry:
        return cls(
            signature=data["signature"],
            step_signatures=data.get("step_signatures", []),
            count=data.get("count", 0),
            first_seen=data.get("first_seen"),
            last_seen=data.get("last_seen"),
            screen_id=data.get("screen_id", ""),
            sop_generated=data.get("sop_generated"),
            test_generated=data.get("test_generated"),
            examples=data.get("examples", []),
        )
