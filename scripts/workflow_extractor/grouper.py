"""
Grouper — the core workflow extraction engine.

1. Groups AuditRecords by BatchID into Operations
2. Chains Operations into WorkflowPaths by tracking entity keys over time
3. Detects recurring patterns by hashing step signatures
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Optional

from .models import AuditRecord, Operation, WorkflowPath


# ── System usernames to exclude ──────────────────────────────────────────────

SYSTEM_USERS = frozenset({
    "admin",
    "system",
    "api-bot",
    "SYSTEM",
})


# ── Grouping ─────────────────────────────────────────────────────────────────

def group_by_batch(records: list[AuditRecord]) -> list[Operation]:
    """Group records by BatchID into Operations.

    Each Operation represents one user "Save" in Acumatica.
    Records within a batch are ordered by ChangeID.
    """
    batches: dict[int, list[AuditRecord]] = defaultdict(list)
    for r in records:
        batches[r.batch_id].append(r)

    operations = []
    for batch_id in sorted(batches.keys()):
        batch_records = sorted(batches[batch_id], key=lambda r: r.change_id)
        operations.append(Operation(batch_id=batch_id, records=batch_records))

    return operations


def filter_operations(
    operations: list[Operation],
    exclude_users: Optional[set[str]] = None,
    merge_rapid_updates_seconds: float = 2.0,
) -> list[Operation]:
    """Filter noise from operations.

    - Excludes operations by system users
    - Merges rapid-fire updates (same screen+entity within N seconds)
    """
    exclude = exclude_users or SYSTEM_USERS
    filtered = []

    for op in operations:
        # Skip system user operations
        if op.username and op.username in exclude:
            continue
        filtered.append(op)

    if merge_rapid_updates_seconds <= 0:
        return filtered

    # Merge rapid-fire updates: if two consecutive operations affect
    # the same screen+entity within N seconds, merge into one
    merged = []
    for op in filtered:
        if merged:
            prev = merged[-1]
            time_diff = abs((op.change_date - prev.change_date).total_seconds())
            if (time_diff <= merge_rapid_updates_seconds
                    and op.screen_id == prev.screen_id
                    and op.entity_key == prev.entity_key):
                # Merge: extend previous operation's records
                prev.records.extend(op.records)
                continue
        merged.append(op)

    return merged


# ── Workflow path chaining ───────────────────────────────────────────────────

def chain_into_paths(
    operations: list[Operation],
    max_gap_hours: float = 24.0,
) -> list[WorkflowPath]:
    """Chain operations into workflow paths by entity key.

    Groups consecutive operations on the same entity (by entity_key)
    into a single WorkflowPath. A new path starts when:
    - The entity key changes
    - There's a gap of > max_gap_hours between operations
    - The operation is a "Created" (new entity lifecycle)

    Returns paths sorted by first operation date.
    """
    # Group by screen_id + entity_key
    entity_ops: dict[str, list[Operation]] = defaultdict(list)
    for op in operations:
        key = f"{op.screen_id}:{op.entity_key}"
        entity_ops[key].append(op)

    paths = []
    for compound_key, ops in entity_ops.items():
        screen_id = ops[0].screen_id
        entity_key = ops[0].entity_key

        # Sort by date
        ops.sort(key=lambda o: o.change_date)

        # Split into paths at lifecycle boundaries
        current_path_ops: list[Operation] = []
        for op in ops:
            should_split = False

            if not current_path_ops:
                pass  # first operation
            elif op.primary_operation == "Created":
                should_split = True  # new entity lifecycle
            else:
                gap = (op.change_date - current_path_ops[-1].change_date)
                if gap > timedelta(hours=max_gap_hours):
                    should_split = True

            if should_split and current_path_ops:
                paths.append(WorkflowPath(
                    screen_id=screen_id,
                    entity_key=entity_key,
                    operations=current_path_ops,
                ))
                current_path_ops = []

            current_path_ops.append(op)

        if current_path_ops:
            paths.append(WorkflowPath(
                screen_id=screen_id,
                entity_key=entity_key,
                operations=current_path_ops,
            ))

    paths.sort(key=lambda p: p.first_date)
    return paths


# ── Pattern detection ────────────────────────────────────────────────────────

def signature_hash(signature: str) -> str:
    """Short hash of a workflow signature for use as catalog key."""
    return hashlib.sha256(signature.encode()).hexdigest()[:12]


def detect_patterns(
    paths: list[WorkflowPath],
) -> dict[str, list[WorkflowPath]]:
    """Group workflow paths by their signature.

    Returns a dict of signature_hash -> list of paths with that signature.
    Paths with the same signature represent the same recurring workflow.
    """
    pattern_groups: dict[str, list[WorkflowPath]] = defaultdict(list)
    for path in paths:
        h = signature_hash(path.signature)
        pattern_groups[h].append(path)

    return pattern_groups


# ── Full pipeline ────────────────────────────────────────────────────────────

def extract_patterns(
    records: list[AuditRecord],
    exclude_users: Optional[set[str]] = None,
    merge_rapid_seconds: float = 2.0,
    max_gap_hours: float = 24.0,
) -> dict[str, list[WorkflowPath]]:
    """Full extraction pipeline: records → operations → paths → patterns.

    Returns dict of signature_hash -> list of WorkflowPaths.
    """
    operations = group_by_batch(records)
    operations = filter_operations(
        operations,
        exclude_users=exclude_users,
        merge_rapid_updates_seconds=merge_rapid_seconds,
    )
    paths = chain_into_paths(operations, max_gap_hours=max_gap_hours)
    return detect_patterns(paths)
