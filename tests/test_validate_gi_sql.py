"""Tests for validate_gi_sql() — destructive SQL detection for GI tables.

Blocks INSERT INTO GI*, DELETE FROM GI*, UPDATE GI*, DROP TABLE GI*,
TRUNCATE TABLE GI*, ALTER TABLE GI* unless code contains the explicit
review marker: -- REVIEWED: gi-sql-safe

See AAR 2026-03-29: SQL INSERT against GI tables bricked production for 45 min.
"""

import sys
from pathlib import Path

# Add scripts/ to path so we can import validate-project
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

# Import using importlib since the module name has a hyphen
import importlib

validate_project = importlib.import_module("validate-project")
validate_gi_sql = validate_project.validate_gi_sql


def _reset_errors():
    """Clear the global errors list between tests."""
    validate_project.errors.clear()


def _error_count():
    return len(validate_project.errors)


class TestInsertBlocked:
    def test_insert_into_gidesign(self):
        _reset_errors()
        code = 'string sql = "INSERT INTO GIDesign (DesignID, Name) VALUES (@p0, @p1)";'
        validate_gi_sql("TestClass", code)
        assert _error_count() == 1

    def test_insert_into_gi_case_insensitive(self):
        _reset_errors()
        code = 'string sql = "insert into GIFilter (FilterID) values (@p0)";'
        validate_gi_sql("TestClass", code)
        assert _error_count() == 1

    def test_insert_into_gi_extra_whitespace(self):
        _reset_errors()
        code = 'string sql = "INSERT   INTO   GISort (SortID) VALUES (@p0)";'
        validate_gi_sql("TestClass", code)
        assert _error_count() == 1


class TestDeleteBlocked:
    def test_delete_from_giresult(self):
        _reset_errors()
        code = 'string sql = "DELETE FROM GIResult WHERE DesignID = @p0";'
        validate_gi_sql("TestClass", code)
        assert _error_count() == 1

    def test_delete_from_gi_case_insensitive(self):
        _reset_errors()
        code = 'string sql = "delete from GIWhere WHERE ID = 1";'
        validate_gi_sql("TestClass", code)
        assert _error_count() == 1


class TestUpdateBlocked:
    def test_update_giwhere(self):
        _reset_errors()
        code = 'string sql = "UPDATE GIWhere SET Value = @p0 WHERE ID = @p1";'
        validate_gi_sql("TestClass", code)
        assert _error_count() == 1


class TestDropTruncateAlterBlocked:
    def test_drop_table_gidesign(self):
        _reset_errors()
        code = 'string sql = "DROP TABLE GIDesign";'
        validate_gi_sql("TestClass", code)
        assert _error_count() == 1

    def test_truncate_table_gifilter(self):
        _reset_errors()
        code = 'string sql = "TRUNCATE TABLE GIFilter";'
        validate_gi_sql("TestClass", code)
        assert _error_count() == 1

    def test_alter_table_gisort(self):
        _reset_errors()
        code = 'string sql = "ALTER TABLE GISort ADD COLUMN Foo INT";'
        validate_gi_sql("TestClass", code)
        assert _error_count() == 1


class TestReviewMarkerAllowed:
    def test_insert_with_review_marker(self):
        _reset_errors()
        code = (
            '-- REVIEWED: gi-sql-safe\n'
            'string sql = "INSERT INTO GIDesign (DesignID, Name) VALUES (@p0, @p1)";'
        )
        validate_gi_sql("TestClass", code)
        assert _error_count() == 0

    def test_delete_with_review_marker(self):
        _reset_errors()
        code = (
            'string sql = "DELETE FROM GIResult WHERE ID = 1";\n'
            '-- REVIEWED: gi-sql-safe\n'
        )
        validate_gi_sql("TestClass", code)
        assert _error_count() == 0


class TestNonGiSqlAllowed:
    def test_insert_into_mytable(self):
        _reset_errors()
        code = 'string sql = "INSERT INTO MyTable (Col1) VALUES (@p0)";'
        validate_gi_sql("TestClass", code)
        assert _error_count() == 0

    def test_delete_from_regular_table(self):
        _reset_errors()
        code = 'string sql = "DELETE FROM OrderLine WHERE ID = 1";'
        validate_gi_sql("TestClass", code)
        assert _error_count() == 0

    def test_update_regular_table(self):
        _reset_errors()
        code = 'string sql = "UPDATE SOOrder SET Status = @p0";'
        validate_gi_sql("TestClass", code)
        assert _error_count() == 0

    def test_select_from_gi_tables_allowed(self):
        """SELECT from GI tables is read-only and safe."""
        _reset_errors()
        code = 'string sql = "SELECT * FROM GIDesign WHERE DesignID = @p0";'
        validate_gi_sql("TestClass", code)
        assert _error_count() == 0
