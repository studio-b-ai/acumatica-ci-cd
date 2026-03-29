"""Test that the UserAuditTrail POC generates valid SQL."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from poc_user_audit_trail import build_user_audit_trail_spec, MOCK_SCHEMA, TEMPLATE_ROW
from gi_builder import GIBuilder
from gi_schema import GISchemaMap


def test_user_audit_trail_sql_generates():
    schema = GISchemaMap(MOCK_SCHEMA, "24.200.001")
    spec = build_user_audit_trail_spec()
    builder = GIBuilder(schema, template_row=TEMPLATE_ROW, company_id=2)
    sql = builder.build_sql(spec)

    assert "-- REVIEWED: gi-sql-safe" in sql
    assert "UserAuditTrail" in sql
    assert "BEGIN TRANSACTION" in sql
    assert "COMMIT" in sql
    assert "INSERT INTO GIDesign" in sql
    assert "INSERT INTO GITable" in sql
    assert sql.count("INSERT INTO GIResult") == 9  # 9 result columns
    assert sql.count("INSERT INTO GIFilter") == 3  # 3 filters
    assert sql.count("INSERT INTO GIWhere") == 3   # 3 where conditions
    assert sql.count("INSERT INTO GISort") == 1    # 1 sort column
    assert "IF EXISTS" in sql  # idempotency check
    assert "PX.SM.AuditHistory" in sql
    assert "AuditHistory.ChangeDate" in sql
