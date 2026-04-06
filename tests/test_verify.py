"""Tests for scripts/verify.py — unified post-publish verification."""
import json
import sys
import os
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import asdict

import pytest

# Ensure scripts/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.verify import (
    CheckStatus,
    CheckResult,
    VerifyResult,
    classify_http_status,
    AcumaticaSession,
    check_entity_reachability,
    check_custom_fields,
    run_e2e_probe,
    check_gi_health,
    compute_overall,
    build_summary,
    run_all_checks,
)


# ---------------------------------------------------------------------------
# classify_http_status
# ---------------------------------------------------------------------------

class TestClassifyHttpStatus:
    def test_200_is_pass(self):
        status, detail = classify_http_status(200)
        assert status == "pass"

    def test_204_is_pass(self):
        status, detail = classify_http_status(204)
        assert status == "pass"

    def test_401_is_fail(self):
        status, detail = classify_http_status(401)
        assert status == "fail"
        assert "auth" in detail.lower()

    def test_403_is_warn_not_fail(self):
        """403 MUST be WARN, never FAIL — this is a hard requirement."""
        status, detail = classify_http_status(403)
        assert status == "warn"
        assert "permission" in detail.lower()

    def test_404_is_fail(self):
        status, detail = classify_http_status(404)
        assert status == "fail"
        assert "missing" in detail.lower() or "not found" in detail.lower()

    def test_500_is_fail(self):
        status, detail = classify_http_status(500)
        assert status == "fail"
        assert "server error" in detail.lower()

    def test_502_is_fail(self):
        status, detail = classify_http_status(502)
        assert status == "fail"

    def test_500_with_body_includes_snippet(self):
        body = "A" * 300
        status, detail = classify_http_status(500, response_body=body)
        assert status == "fail"
        assert len(detail) <= 300  # detail shouldn't be massive
        assert "A" * 50 in detail  # should contain some of the body

    def test_500_body_truncated_to_200_chars(self):
        body = "X" * 400
        status, detail = classify_http_status(500, response_body=body)
        # The body snippet in detail should be at most 200 chars
        assert "X" * 200 in detail
        assert "X" * 201 not in detail


# ---------------------------------------------------------------------------
# compute_overall / build_summary
# ---------------------------------------------------------------------------

class TestComputeOverall:
    def test_all_pass(self):
        checks = [
            CheckResult("a", CheckStatus.PASS, "ok"),
            CheckResult("b", CheckStatus.PASS, "ok"),
        ]
        assert compute_overall(checks) == "pass"

    def test_any_fail_means_fail(self):
        checks = [
            CheckResult("a", CheckStatus.PASS, "ok"),
            CheckResult("b", CheckStatus.FAIL, "bad"),
        ]
        assert compute_overall(checks) == "fail"

    def test_warn_only_is_pass(self):
        checks = [
            CheckResult("a", CheckStatus.PASS, "ok"),
            CheckResult("b", CheckStatus.WARN, "permission issue"),
        ]
        assert compute_overall(checks) == "pass"

    def test_empty_checks_is_pass(self):
        assert compute_overall([]) == "pass"


class TestBuildSummary:
    def test_summary_format(self):
        checks = [
            CheckResult("a", CheckStatus.PASS, "ok"),
            CheckResult("b", CheckStatus.WARN, "perm"),
            CheckResult("c", CheckStatus.FAIL, "bad"),
            CheckResult("d", CheckStatus.PASS, "ok"),
        ]
        summary = build_summary(checks)
        assert "2 pass" in summary
        assert "1 warn" in summary
        assert "1 fail" in summary

    def test_empty_summary(self):
        summary = build_summary([])
        assert "0 pass" in summary
        assert "0 fail" in summary


# ---------------------------------------------------------------------------
# AcumaticaSession (mock HTTP layer)
# ---------------------------------------------------------------------------

class FakeHTTPResponse:
    """Minimal fake for urllib response objects."""
    def __init__(self, status, body=b"", headers=None):
        self.status = status
        self._body = body
        self.headers = headers or {}

    def read(self):
        return self._body

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestAcumaticaSession:
    def test_login_success(self):
        session = AcumaticaSession("https://acumatica.example.com", "admin", "pass", "Main")
        fake_resp = FakeHTTPResponse(204)
        with patch.object(session, "_request", return_value=(204, b"")) as mock_req:
            session.login()
            # Should call auth/login
            call_args = mock_req.call_args
            assert "auth/login" in call_args[0][1].lower() or "auth/login" in str(call_args).lower()

    def test_login_failure_raises(self):
        session = AcumaticaSession("https://acumatica.example.com", "admin", "bad", "Main")
        with patch.object(session, "_request", return_value=(401, b"Unauthorized")):
            with pytest.raises(Exception):
                session.login()

    def test_get_returns_status_and_body(self):
        session = AcumaticaSession("https://acumatica.example.com", "admin", "pass", "Main")
        session._cookies = "ASP.NET_SessionId=abc123"
        body = b'[{"id": 1}]'
        with patch.object(session, "_request", return_value=(200, body)):
            status, data = session.get("/entity/Default/24.200.001/StockItem")
            assert status == 200
            assert data == body


# ---------------------------------------------------------------------------
# check_entity_reachability
# ---------------------------------------------------------------------------

class TestEntityReachability:
    def test_200_pass(self):
        session = MagicMock()
        session.get.return_value = (200, b'[]')
        session.base_url = "https://example.com"
        result = check_entity_reachability(session, "PurchaseOrder", "24.200.001")
        assert result.status == CheckStatus.PASS
        assert result.name == "entity:PurchaseOrder"
        assert result.http_code == 200

    def test_404_fail(self):
        session = MagicMock()
        session.get.return_value = (404, b'Not Found')
        session.base_url = "https://example.com"
        result = check_entity_reachability(session, "PurchaseOrder", "24.200.001")
        assert result.status == CheckStatus.FAIL
        assert result.http_code == 404

    def test_403_warn(self):
        session = MagicMock()
        session.get.return_value = (403, b'Forbidden')
        session.base_url = "https://example.com"
        result = check_entity_reachability(session, "Vendor", "24.200.001")
        assert result.status == CheckStatus.WARN
        assert result.http_code == 403

    def test_500_includes_body_snippet(self):
        session = MagicMock()
        body = b"Internal error: DAC cache corrupted " + b"x" * 300
        session.get.return_value = (500, body)
        session.base_url = "https://example.com"
        result = check_entity_reachability(session, "StockItem", "24.200.001")
        assert result.status == CheckStatus.FAIL
        assert result.http_code == 500
        assert "Internal error" in result.detail


# ---------------------------------------------------------------------------
# check_custom_fields
# ---------------------------------------------------------------------------

class TestCustomFields:
    def test_fields_present(self):
        session = MagicMock()
        schema_body = json.dumps({
            "custom.Document.UsrExpArrivalDate": {"type": "string"},
            "custom.Document.UsrContainerRef": {"type": "string"},
        }).encode()
        session.get.return_value = (200, schema_body)
        session.base_url = "https://example.com"
        fields = ["custom.Document.UsrExpArrivalDate", "custom.Document.UsrContainerRef"]
        results = check_custom_fields(session, "PurchaseOrder", "24.200.001", fields)
        assert len(results) == 2
        assert all(r.status == CheckStatus.PASS for r in results)

    def test_field_missing(self):
        session = MagicMock()
        schema_body = json.dumps({
            "custom.Document.UsrExpArrivalDate": {"type": "string"},
        }).encode()
        session.get.return_value = (200, schema_body)
        session.base_url = "https://example.com"
        fields = ["custom.Document.UsrExpArrivalDate", "custom.Document.UsrMissing"]
        results = check_custom_fields(session, "PurchaseOrder", "24.200.001", fields)
        assert results[0].status == CheckStatus.PASS
        assert results[1].status == CheckStatus.FAIL
        assert "UsrMissing" in results[1].detail

    def test_schema_endpoint_403_all_warn(self):
        session = MagicMock()
        session.get.return_value = (403, b'Forbidden')
        session.base_url = "https://example.com"
        fields = ["custom.Document.UsrFoo"]
        results = check_custom_fields(session, "PurchaseOrder", "24.200.001", fields)
        assert len(results) == 1
        assert results[0].status == CheckStatus.WARN

    def test_empty_fields_returns_empty(self):
        session = MagicMock()
        session.base_url = "https://example.com"
        results = check_custom_fields(session, "PurchaseOrder", "24.200.001", [])
        assert results == []

    def test_schema_endpoint_500(self):
        session = MagicMock()
        session.get.return_value = (500, b'Server Error')
        session.base_url = "https://example.com"
        fields = ["custom.Document.UsrFoo"]
        results = check_custom_fields(session, "PurchaseOrder", "24.200.001", fields)
        assert len(results) == 1
        assert results[0].status == CheckStatus.FAIL


# ---------------------------------------------------------------------------
# run_e2e_probe
# ---------------------------------------------------------------------------

class TestE2EProbe:
    def test_probe_success(self):
        session = MagicMock()
        session.get.return_value = (200, b'[{"VendorID": "V001"}]')
        session.base_url = "https://example.com"
        probe = {"entity": "Vendor", "select_fields": ["VendorID", "UsrDefaultInTransitSiteID"]}
        result = run_e2e_probe(session, probe, "24.200.001")
        assert result.status == CheckStatus.PASS
        assert result.name == "e2e:Vendor"
        assert result.http_code == 200

    def test_probe_500_fail(self):
        session = MagicMock()
        session.get.return_value = (500, b'View resolution failed')
        session.base_url = "https://example.com"
        probe = {"entity": "StockItem", "select_fields": ["InventoryID", "UsrHTSCode"]}
        result = run_e2e_probe(session, probe, "24.200.001")
        assert result.status == CheckStatus.FAIL
        assert result.http_code == 500
        assert "View resolution" in result.detail

    def test_probe_403_warn(self):
        session = MagicMock()
        session.get.return_value = (403, b'Forbidden')
        session.base_url = "https://example.com"
        probe = {"entity": "Vendor", "select_fields": ["VendorID"]}
        result = run_e2e_probe(session, probe, "24.200.001")
        assert result.status == CheckStatus.WARN


# ---------------------------------------------------------------------------
# check_gi_health
# ---------------------------------------------------------------------------

class TestGIHealth:
    def test_all_healthy(self):
        session = MagicMock()
        session.get.return_value = (200, b'[]')
        session.base_url = "https://example.com"
        results = check_gi_health(session, "24.200.001")
        assert isinstance(results, list)
        assert len(results) >= 2  # InventoryAllocationDetail + LotAvailability
        assert all(r.status == CheckStatus.PASS for r in results)

    def test_one_gi_fails(self):
        session = MagicMock()
        session.get.side_effect = [
            (500, b'GI corrupted'),
            (200, b'[]'),
        ]
        session.base_url = "https://example.com"
        results = check_gi_health(session, "24.200.001")
        statuses = [r.status for r in results]
        assert CheckStatus.FAIL in statuses
        assert CheckStatus.PASS in statuses

    def test_all_gi_fail(self):
        session = MagicMock()
        session.get.return_value = (500, b'Server Error')
        session.base_url = "https://example.com"
        results = check_gi_health(session, "24.200.001")
        assert all(r.status == CheckStatus.FAIL for r in results)

    def test_gi_exception_handled(self):
        session = MagicMock()
        session.get.side_effect = Exception("Connection timeout")
        session.base_url = "https://example.com"
        results = check_gi_health(session, "24.200.001")
        assert all(r.status == CheckStatus.FAIL for r in results)


# ---------------------------------------------------------------------------
# run_all_checks (integration with manifest)
# ---------------------------------------------------------------------------

class TestRunAllChecks:
    @pytest.fixture
    def sample_manifest(self):
        return {
            "entities": {
                "PurchaseOrder": {
                    "screen": "PO301000",
                    "custom_fields": ["custom.Document.UsrExpArrivalDate"],
                },
                "Vendor": {
                    "screen": "AP303000",
                    "custom_fields": [],
                },
            },
            "e2e_probes": [
                {"entity": "Vendor", "select_fields": ["VendorID", "UsrDefaultInTransitSiteID"]},
            ],
        }

    def test_run_all_checks_happy_path(self, sample_manifest):
        session = MagicMock()
        # All GETs return 200
        session.get.return_value = (200, json.dumps({"custom.Document.UsrExpArrivalDate": {}}).encode())
        session.base_url = "https://example.com"
        checks = run_all_checks(session, sample_manifest, "24.200.001")
        assert len(checks) > 0
        # Should have entity checks, custom field checks, e2e probes, and GI health
        names = [c.name for c in checks]
        assert "entity:PurchaseOrder" in names
        assert "entity:Vendor" in names
        assert any("field:" in n for n in names)
        assert "e2e:Vendor" in names
        assert any("gi:" in n for n in names)

    def test_run_all_checks_skips_empty_custom_fields(self, sample_manifest):
        session = MagicMock()
        session.get.return_value = (200, b'[]')
        session.base_url = "https://example.com"
        checks = run_all_checks(session, sample_manifest, "24.200.001")
        # Vendor has no custom_fields, so no field: checks for Vendor
        field_checks = [c for c in checks if c.name.startswith("field:") and "Vendor" in c.name]
        assert len(field_checks) == 0


# ---------------------------------------------------------------------------
# VerifyResult serialization
# ---------------------------------------------------------------------------

class TestVerifyResult:
    def test_to_dict(self):
        checks = [
            CheckResult("login", CheckStatus.PASS, "ok", 204),
            CheckResult("entity:Vendor", CheckStatus.WARN, "permission issue", 403),
        ]
        vr = VerifyResult(
            overall="pass",
            environment="sandbox",
            checks=checks,
            summary="1 pass, 1 warn, 0 fail",
        )
        d = vr.to_dict()
        assert d["overall"] == "pass"
        assert d["environment"] == "sandbox"
        assert len(d["checks"]) == 2
        assert d["checks"][0]["name"] == "login"
        assert d["checks"][1]["http_code"] == 403

    def test_json_roundtrip(self):
        checks = [CheckResult("login", CheckStatus.PASS, "ok", 204)]
        vr = VerifyResult(
            overall="pass",
            environment="production",
            checks=checks,
            summary="1 pass, 0 warn, 0 fail",
        )
        json_str = json.dumps(vr.to_dict())
        parsed = json.loads(json_str)
        assert parsed["overall"] == "pass"
        assert parsed["checks"][0]["status"] == "pass"


# ---------------------------------------------------------------------------
# CheckResult dataclass
# ---------------------------------------------------------------------------

class TestCheckResult:
    def test_default_http_code_none(self):
        r = CheckResult("test", CheckStatus.PASS, "ok")
        assert r.http_code is None

    def test_to_dict(self):
        r = CheckResult("test", CheckStatus.FAIL, "broken", 500)
        d = r.to_dict()
        assert d["name"] == "test"
        assert d["status"] == "fail"
        assert d["detail"] == "broken"
        assert d["http_code"] == 500
