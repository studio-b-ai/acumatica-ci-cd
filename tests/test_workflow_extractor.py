"""
Tests for workflow_extractor models and parser.
"""

import sys
import os
from datetime import datetime

# Add scripts/ to path so we can import workflow_extractor
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from workflow_extractor.parser import (
    parse_combined_key,
    parse_modified_fields,
    parse_odata_record,
    parse_odata_response,
    screen_name,
)
from workflow_extractor.models import (
    AuditRecord,
    Operation,
    WorkflowPath,
    PatternEntry,
)
from workflow_extractor.grouper import (
    group_by_batch,
    filter_operations,
    chain_into_paths,
    extract_patterns,
    signature_hash,
)
from workflow_extractor.catalog import PatternCatalog


# ── Parser tests ─────────────────────────────────────────────────────────────


class TestParseCombinedKey:
    def test_simple_key(self):
        assert parse_combined_key("CO\x00S000201") == ["CO", "S000201"]

    def test_three_segment_key(self):
        assert parse_combined_key("CO\x00S000201\x001") == ["CO", "S000201", "1"]

    def test_four_segment_key(self):
        assert parse_combined_key("CO\x00S000201\x001\x003") == ["CO", "S000201", "1", "3"]

    def test_empty_string(self):
        assert parse_combined_key("") == []

    def test_single_segment(self):
        assert parse_combined_key("ADMIN") == ["ADMIN"]


class TestParseModifiedFields:
    def test_simple_pair(self):
        result = parse_modified_fields("Qty\x0010")
        assert result == {"Qty": "10"}

    def test_multiple_pairs(self):
        result = parse_modified_fields("Qty\x0010\x00UOM\x00CUT")
        assert result == {"Qty": "10", "UOM": "CUT"}

    def test_empty_value(self):
        result = parse_modified_fields("DiscountsAppliedToLine\x00")
        assert result == {"DiscountsAppliedToLine": ""}

    def test_empty_string(self):
        assert parse_modified_fields("") == {}

    def test_real_data(self):
        raw = "Behavior\x00SO\x00Operation\x00I\x00InvtMult\x00-1"
        result = parse_modified_fields(raw)
        assert result == {"Behavior": "SO", "Operation": "I", "InvtMult": "-1"}

    def test_boolean_values(self):
        raw = "IsStockItem\x00True\x00IsAllocated\x00True"
        result = parse_modified_fields(raw)
        assert result == {"IsStockItem": "True", "IsAllocated": "True"}


class TestParseOdataRecord:
    def test_full_record(self):
        row = {
            "BatchID": "1824",
            "ChangeID": "1824",
            "ScreenID": "SO301000",
            "Operation": "Created",
            "ChangeDate": "2025-08-07T18:17:11.943",
            "TableName": "SOLineSplit",
            "CombinedKey": "CO\x00S000201\x001\x003",
            "ModifiedFields": "Qty\x0010\x00UOM\x00CUT",
        }
        record = parse_odata_record(row)
        assert record.batch_id == 1824
        assert record.change_id == 1824
        assert record.screen_id == "SO301000"
        assert record.operation == "Created"
        assert record.table_name == "SOLineSplit"
        assert record.combined_key == ["CO", "S000201", "1", "3"]
        assert record.modified_fields == {"Qty": "10", "UOM": "CUT"}
        assert record.change_date.year == 2025

    def test_missing_fields_dont_crash(self):
        record = parse_odata_record({})
        assert record.batch_id == 0
        assert record.screen_id == ""
        assert record.combined_key == []
        assert record.modified_fields == {}

    def test_username_field(self):
        row = {
            "BatchID": "1", "ChangeID": "1", "ScreenID": "SO301000",
            "Operation": "Created", "ChangeDate": "2025-01-01T00:00:00",
            "TableName": "SOOrder", "CombinedKey": "", "ModifiedFields": "",
            "Username": "warehouse01",
        }
        record = parse_odata_record(row)
        assert record.username == "warehouse01"


class TestScreenName:
    def test_known_screen(self):
        assert screen_name("SO301000") == "Sales Orders"
        assert screen_name("PO301000") == "Purchase Orders"

    def test_unknown_screen(self):
        assert screen_name("XX999000") == "XX999000"


# ── Model tests ──────────────────────────────────────────────────────────────


def _make_record(batch_id=1, screen_id="SO301000", operation="Created",
                 table_name="SOOrder", key=None, fields=None) -> AuditRecord:
    return AuditRecord(
        batch_id=batch_id,
        change_id=batch_id,
        screen_id=screen_id,
        operation=operation,
        change_date=datetime(2025, 8, 7, 18, 17, 11),
        table_name=table_name,
        combined_key=key or ["CO", "S000201"],
        modified_fields=fields or {},
    )


class TestAuditRecord:
    def test_step_signature(self):
        r = _make_record(operation="Created", table_name="SOOrder")
        assert r.step_signature == "SO301000:Created:SOOrder"


class TestOperation:
    def test_basic_operation(self):
        records = [
            _make_record(table_name="SOOrder", operation="Created"),
            _make_record(table_name="SOLine", operation="Created"),
            _make_record(table_name="SOLineSplit", operation="Created"),
        ]
        op = Operation(batch_id=1, records=records)
        assert op.screen_id == "SO301000"
        assert op.primary_operation == "Created"
        assert op.tables_affected == ["SOOrder", "SOLine", "SOLineSplit"]

    def test_entity_key_picks_shortest(self):
        records = [
            _make_record(key=["CO", "S000201"]),
            _make_record(key=["CO", "S000201", "1"]),
            _make_record(key=["CO", "S000201", "1", "3"]),
        ]
        op = Operation(batch_id=1, records=records)
        assert op.entity_key == "CO|S000201"

    def test_signature_deduplicates(self):
        records = [
            _make_record(operation="Modified", table_name="SOLine"),
            _make_record(operation="Modified", table_name="SOLine"),
        ]
        op = Operation(batch_id=1, records=records)
        assert op.signature == "SO301000:Modified:SOLine"

    def test_primary_operation_priority(self):
        # Created takes priority
        records = [
            _make_record(operation="Modified"),
            _make_record(operation="Created"),
        ]
        op = Operation(batch_id=1, records=records)
        assert op.primary_operation == "Created"

        # Deleted takes priority over Modified
        records = [
            _make_record(operation="Modified"),
            _make_record(operation="Deleted"),
        ]
        op = Operation(batch_id=1, records=records)
        assert op.primary_operation == "Deleted"


class TestPatternEntry:
    def test_add_observation(self):
        pattern = PatternEntry(
            signature="test",
            step_signatures=["SO301000:Created:SOOrder"],
        )
        path = WorkflowPath(
            screen_id="SO301000",
            entity_key="CO|S000201",
            operations=[Operation(batch_id=1, records=[_make_record()])],
        )
        pattern.add_observation(path)
        assert pattern.count == 1
        assert pattern.first_seen is not None
        assert len(pattern.examples) == 1

    def test_threshold_crossing(self):
        pattern = PatternEntry(
            signature="test",
            step_signatures=[],
            count=2,
        )
        assert not pattern.crossed_threshold(3)
        assert not pattern.above_threshold(3)

        pattern.count = 3
        assert pattern.crossed_threshold(3)
        assert pattern.above_threshold(3)

        pattern.count = 4
        assert not pattern.crossed_threshold(3)
        assert pattern.above_threshold(3)

    def test_serialization_roundtrip(self):
        pattern = PatternEntry(
            signature="SO301000:Created:SOOrder",
            step_signatures=["SO301000:Created:SOOrder"],
            count=5,
            first_seen="2025-08-07T18:17:11",
            last_seen="2025-09-01T10:00:00",
            screen_id="SO301000",
            examples=[{"entity_key": "CO|S000201", "username": "admin", "date": "2025-08-07"}],
        )
        d = pattern.to_dict()
        restored = PatternEntry.from_dict(d)
        assert restored.signature == pattern.signature
        assert restored.count == pattern.count
        assert restored.first_seen == pattern.first_seen
        assert len(restored.examples) == 1


# ── Grouper tests ────────────────────────────────────────────────────────────


def _make_record_at(batch_id, change_id, screen_id="SO301000", operation="Modified",
                    table_name="SOOrder", key=None, dt=None, username=None) -> AuditRecord:
    return AuditRecord(
        batch_id=batch_id,
        change_id=change_id,
        screen_id=screen_id,
        operation=operation,
        change_date=dt or datetime(2025, 8, 7, 18, 17, 11),
        table_name=table_name,
        combined_key=key or ["CO", "S000201"],
        modified_fields={},
        username=username,
    )


class TestGroupByBatch:
    def test_groups_by_batch_id(self):
        records = [
            _make_record_at(1, 1, table_name="SOOrder"),
            _make_record_at(1, 2, table_name="SOLine"),
            _make_record_at(2, 3, table_name="SOOrder"),
        ]
        ops = group_by_batch(records)
        assert len(ops) == 2
        assert ops[0].batch_id == 1
        assert len(ops[0].records) == 2
        assert ops[1].batch_id == 2
        assert len(ops[1].records) == 1

    def test_sorts_within_batch_by_change_id(self):
        records = [
            _make_record_at(1, 3, table_name="SOLineSplit"),
            _make_record_at(1, 1, table_name="SOOrder"),
            _make_record_at(1, 2, table_name="SOLine"),
        ]
        ops = group_by_batch(records)
        assert ops[0].records[0].table_name == "SOOrder"
        assert ops[0].records[1].table_name == "SOLine"
        assert ops[0].records[2].table_name == "SOLineSplit"


class TestFilterOperations:
    def test_excludes_system_users(self):
        records = [_make_record_at(1, 1, username="admin")]
        ops = group_by_batch(records)
        filtered = filter_operations(ops)
        assert len(filtered) == 0

    def test_keeps_non_system_users(self):
        records = [_make_record_at(1, 1, username="warehouse01")]
        ops = group_by_batch(records)
        filtered = filter_operations(ops)
        assert len(filtered) == 1

    def test_merges_rapid_updates(self):
        dt1 = datetime(2025, 8, 7, 18, 0, 0)
        dt2 = datetime(2025, 8, 7, 18, 0, 1)  # 1 second later
        dt3 = datetime(2025, 8, 7, 18, 1, 0)  # 60 seconds later
        records = [
            _make_record_at(1, 1, dt=dt1, username="warehouse01"),
            _make_record_at(2, 2, dt=dt2, username="warehouse01"),
            _make_record_at(3, 3, dt=dt3, username="warehouse01"),
        ]
        ops = group_by_batch(records)
        filtered = filter_operations(ops, merge_rapid_updates_seconds=2.0)
        assert len(filtered) == 2  # first two merged, third separate


class TestChainIntoPaths:
    def test_same_entity_same_path(self):
        dt1 = datetime(2025, 8, 7, 18, 0, 0)
        dt2 = datetime(2025, 8, 7, 18, 5, 0)
        records = [
            _make_record_at(1, 1, operation="Created", dt=dt1),
            _make_record_at(2, 2, operation="Modified", dt=dt2),
        ]
        ops = group_by_batch(records)
        paths = chain_into_paths(ops)
        assert len(paths) == 1
        assert paths[0].step_count == 2

    def test_created_starts_new_path(self):
        dt1 = datetime(2025, 8, 7, 18, 0, 0)
        dt2 = datetime(2025, 8, 7, 18, 5, 0)
        records = [
            _make_record_at(1, 1, operation="Created", dt=dt1),
            _make_record_at(2, 2, operation="Created", dt=dt2),
        ]
        ops = group_by_batch(records)
        paths = chain_into_paths(ops)
        assert len(paths) == 2

    def test_large_gap_splits_path(self):
        dt1 = datetime(2025, 8, 7, 18, 0, 0)
        dt2 = datetime(2025, 8, 9, 18, 0, 0)  # 48 hours later
        records = [
            _make_record_at(1, 1, operation="Modified", dt=dt1),
            _make_record_at(2, 2, operation="Modified", dt=dt2),
        ]
        ops = group_by_batch(records)
        paths = chain_into_paths(ops, max_gap_hours=24.0)
        assert len(paths) == 2


class TestExtractPatterns:
    def test_identical_workflows_group_together(self):
        # Two entities go through the same Create→Modify pattern
        dt1 = datetime(2025, 8, 7, 18, 0, 0)
        dt2 = datetime(2025, 8, 7, 18, 5, 0)
        dt3 = datetime(2025, 8, 8, 10, 0, 0)
        dt4 = datetime(2025, 8, 8, 10, 5, 0)
        records = [
            _make_record_at(1, 1, operation="Created", key=["CO", "S001"], dt=dt1),
            _make_record_at(2, 2, operation="Modified", key=["CO", "S001"], dt=dt2),
            _make_record_at(3, 3, operation="Created", key=["CO", "S002"], dt=dt3),
            _make_record_at(4, 4, operation="Modified", key=["CO", "S002"], dt=dt4),
        ]
        patterns = extract_patterns(records, exclude_users=set())
        # Both paths have the same signature, so they group together
        assert len(patterns) == 1
        paths = list(patterns.values())[0]
        assert len(paths) == 2


# ── Catalog tests ────────────────────────────────────────────────────────────


class TestPatternCatalog:
    def test_threshold_detection(self, tmp_path):
        catalog = PatternCatalog(
            path=str(tmp_path / "test_catalog.json"),
            threshold=3,
        )

        # Create 3 identical workflow paths
        dt = datetime(2025, 8, 7, 18, 0, 0)
        all_paths = []
        for i in range(3):
            records = [_make_record_at(i * 10 + 1, i * 10 + 1,
                                       operation="Created",
                                       key=["CO", f"S00{i}"],
                                       dt=dt)]
            ops = group_by_batch(records)
            path = WorkflowPath(
                screen_id="SO301000",
                entity_key=f"CO|S00{i}",
                operations=ops,
            )
            all_paths.append(path)

        # All have the same signature
        sig = signature_hash(all_paths[0].signature)
        pattern_groups = {sig: all_paths}

        newly_crossed = catalog.update(pattern_groups)
        assert len(newly_crossed) == 1
        assert newly_crossed[0].count == 3

    def test_save_and_reload(self, tmp_path):
        catalog_path = str(tmp_path / "test_catalog.json")
        catalog = PatternCatalog(path=catalog_path, threshold=3)

        dt = datetime(2025, 8, 7, 18, 0, 0)
        records = [_make_record_at(1, 1, operation="Created", dt=dt)]
        ops = group_by_batch(records)
        path = WorkflowPath(screen_id="SO301000", entity_key="CO|S001", operations=ops)
        sig = signature_hash(path.signature)
        catalog.update({sig: [path]})
        catalog.last_fetched = "2025-08-07T18:17:11"
        catalog.save()

        # Reload
        catalog2 = PatternCatalog(path=catalog_path, threshold=3)
        assert catalog2.last_fetched == "2025-08-07T18:17:11"
        assert len(catalog2.patterns) == 1
        assert list(catalog2.patterns.values())[0].count == 1
