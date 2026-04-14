# Acumatica: Custom DAC Fields Require Endpoint Mapping for REST API Writes

**Severity:** Critical — silently drops data
**Discovered:** 2026-03-07 (UsrHubSpotDealId), confirmed 2026-04-13 (UsrWMSStatus)
**Affects:** All DAC extension fields (Usr* fields from PXCacheExtension classes)

## The Problem

Acumatica's Default REST endpoint (v24.200.001) does NOT auto-include DAC extension
fields in its endpoint schema. This means:

- **Reads work** via `GET /SalesOrder/CO/S003424?$custom=Document.UsrWMSStatus` — field appears in response
- **Writes are SILENTLY DROPPED** — `PUT /SalesOrder` with `custom.Document.UsrWMSStatus` returns HTTP 200 but the value is NOT persisted

The API does not error, warn, or indicate that the field was ignored. The response
returns the old value (or null) as if nothing happened.

## Root Cause

The `$custom` query parameter forces the API to include extension fields in the
response for reads, but the endpoint's write schema only processes fields that are
explicitly mapped in the endpoint definition. DAC extension fields that aren't
mapped are silently discarded during PUT processing.

ISV packages (like Ramp, FusionWMS) include endpoint extensions in their
customization packages. Our custom packages (AesthetikWMS, AesthetikContainers)
historically did not.

## The Fix

Every DAC extension field that needs REST API write support MUST be added to the
Default endpoint definition (or a custom endpoint that extends Default).

### Steps (Acumatica UI — SM207060)

1. Navigate to **Web Service Endpoints** (SM207060)
2. Select endpoint: **Default**, version **24.200.001**
3. Click **Extend Endpoint** → name it `AesthetikWMS`, version `24.200.001`
4. In the entity tree, find **SalesOrder**
5. Click **Extend Entity**
6. Click **Populate** to discover available custom fields
7. Check/add each field:
   - `UsrWMSStatus` (SOOrderExt → Document view)
   - `UsrHubSpotDealId` (SOOrderExt → Document view)
   - `UsrComplianceHold` (SOOrderExt → Document view)
   - `UsrComplianceHoldReason` (SOOrderExt → Document view)
8. **Save** the endpoint
9. Include the endpoint extension in the AesthetikWMS customization project:
   - Customization Project Editor → Web Service Endpoints → Add New Record
   - Select `AesthetikWMS` endpoint
   - Save and publish

### After Extension

The fields become writable at the new endpoint path:
```
PUT /entity/AesthetikWMS/24.200.001/SalesOrder
{
  "OrderType": {"value": "CO"},
  "OrderNbr": {"value": "S003424"},
  "UsrWMSStatus": {"value": "A"}
}
```

Or if added to the Default endpoint directly, at the existing path:
```
PUT /entity/default/24.200.001/SalesOrder
{
  "OrderType": {"value": "CO"},
  "OrderNbr": {"value": "S003424"},
  "custom": {"Document": {"UsrWMSStatus": {"value": "A"}}}
}
```

### Verification

After extending, confirm with `$adHocSchema`:
```
GET /entity/AesthetikWMS/24.200.001/SalesOrder/$adHocSchema
```

The `custom.Document` section should now include `UsrWMSStatus` and other mapped fields.

## Checklist: Adding New Custom DAC Fields

When adding a new `Usr*` field to any DAC extension:

- [ ] Add the field to the DAC extension C# class (PXCacheExtension)
- [ ] Add the SQL column creation to project.xml (`<Sql>` element)
- [ ] Add the graph extension if needed (for screen visibility)
- [ ] **Add the field to the REST API endpoint definition** (SM207060)
- [ ] **Include the endpoint extension in the customization project**
- [ ] Test both read (`GET` with `$custom`) and write (`PUT`) via REST API
- [ ] Update heritage-wms / webhook-router code to use the field

## Affected Entities (Heritage Fabrics)

| Entity | DAC Extension | Fields | Endpoint Status |
|--------|--------------|--------|----------------|
| SalesOrder | SOOrderExt | UsrWMSStatus, UsrHubSpotDealId, UsrComplianceHold, UsrComplianceHoldReason | NEEDS MAPPING |
| SOShipment | SOShipmentExt | UsrIncludeInContainer, UsrContainerID | Via ContainerTracking endpoint |
| Customer | CustomerExt | UsrDisablePayLink | NEEDS MAPPING |
| INSetup | INSetupExt | UsrPG* (15 fields) | NEEDS MAPPING |
| INLotSerialClass | INLotSerialClassExt | UsrPG* (4 fields) | NEEDS MAPPING |
| INLotSerialStatus | INLotSerialStatusExt | Usr* (9 fields) | NEEDS MAPPING |

## References

- Acumatica docs: [Extending Web Service Endpoints](https://www.acumatica.com/blog/extending-acumatica-web-service-endpoints/)
- Acumatica community: [Custom fields in endpoints](https://community.acumatica.com/develop-customizations-288/how-to-pass-custom-fields-to-acumatica-endpoint-19462)
- Session history: 2026-03-07 (first identification), 2026-04-13 (root cause confirmed)
