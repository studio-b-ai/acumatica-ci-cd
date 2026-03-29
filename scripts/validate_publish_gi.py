"""GI health check for post-publish verification.

Probes known Generic Inquiries via the Acumatica REST API to detect
GI subsystem corruption (e.g. orphaned GIDesign rows that crash
PXGenericInqGrph+Definition on app pool restart).
"""

PROBE_GIS = [
    "InventoryAllocationDetail",
    "LotAvailability",
]

RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"


def check_gi_health(session, base_url: str) -> bool:
    """Probe the GI subsystem by querying known GIs via REST API.

    Accepts either a requests.Session or an AcumaticaSession (from
    validate-publish.py). For AcumaticaSession, uses query_entity();
    for requests.Session, uses session.get() directly.

    Returns True if at least one GI responds successfully.
    Returns False if ALL probes fail (indicates systemic GI corruption).
    """
    base_url = base_url.rstrip("/")
    any_success = False

    for gi_name in PROBE_GIS:
        try:
            # Support both AcumaticaSession (query_entity) and requests.Session (.get)
            if hasattr(session, "query_entity"):
                code, _body = session.query_entity(gi_name, top=1)
            else:
                resp = session.get(
                    f"{base_url}/entity/Default/24.200.001/{gi_name}",
                    params={"$top": "1"},
                    timeout=30,
                )
                code = resp.status_code

            if code == 200:
                print(f"{GREEN}[  OK  ]{RESET} GI probe: {gi_name} responded (HTTP 200)")
                any_success = True
            else:
                print(f"{RED}[FAIL  ]{RESET} GI probe: {gi_name} returned HTTP {code}")
        except Exception as exc:
            print(f"{RED}[FAIL  ]{RESET} GI probe: {gi_name} error: {exc}")

    if not any_success:
        print(f"{RED}[FAIL  ]{RESET} GI SUBSYSTEM UNHEALTHY — all probes failed")

    return any_success
