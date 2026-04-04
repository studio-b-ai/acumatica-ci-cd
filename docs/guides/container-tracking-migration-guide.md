# Container Tracking Migration Guide

**Audience:** Heritage Fabrics warehouse and logistics team
**Date:** April 2026

---

## What Changed

The IIG Container Management add-on has been removed from our Acumatica system and replaced by **AesthetikContainers**, a custom-built solution owned and maintained by Studio B.

Here is what you need to know:

- **All your container data was migrated.** Nothing was lost -- every container, event, and forwarder record carried over to the new screens.
- **The new screens live in the same place.** Open the **Container Tracking** workspace in the left sidebar, just like before.
- **The layout is cleaner and faster.** The new screens follow Acumatica's standard patterns, so they feel familiar and load quickly.
- **We own the code now.** Bug fixes and new features ship on our schedule, not a third-party vendor's.

---

## Screen Mapping

Use this table to find where your old IIG screens moved.

| Old IIG Screen | Old Screen ID | New Screen | New Screen ID | Status |
|----------------|---------------|------------|---------------|--------|
| PO Containers | IG.CM.01.02 | PO Containers | SB401000 | Live |
| SO Containers | IG.CM.01.04 | SO Containers | SB401010 | Live |
| Container Events | IG.CM.01.06 | Container Events | SB401020 | Live |
| Freight Forwarders | IG.CM.30.91 | Freight Forwarders | SB302000 | Live |
| Custom Classification | IG.CM.30.93 | Custom Classification | SB401030 | Live |
| Container Maintenance | (none) | Container Maintenance | SB501000 | Live (unchanged) |
| Container Types | IG.CM.20.92 | -- | -- | Coming in Phase 3 |
| Container Destinations | IG.CM.20.94 | -- | -- | Coming in Phase 3 |
| Container Preferences | IG.CM.10.10 | -- | -- | Coming in Phase 3 |
| PO Container Lines | IG.CM.00.09 | -- | -- | Coming in Phase 3 |
| Container Distributions | IG.CM.01.03 | -- | -- | Deferred |
| Duty/Tariff Adjustments | IG.CM.05.91 | -- | -- | Deferred |

---

## How to Find the New Screens

1. **Sidebar workspace:** Click **Container Tracking** in the left sidebar navigation. All six active screens are listed there.
2. **Search bar:** Click the magnifying glass icon (or press Ctrl+Space) and type the screen ID -- for example, `SB401000` -- to jump directly to a screen.
3. **Favorites:** Right-click any screen in the workspace list and select **Add to Favorites** for quick access.

---

## Screen-by-Screen Guide

### PO Containers (SB401000)

This is your primary view for tracking inbound purchase order containers. It shows every container record with its current status, carrier, vessel name, origin and destination ports, and key dates (ETD, ETA, actual arrival). Use the **Status** or **Carrier** filters at the top of the grid to narrow down what you see. Click any row to jump to Container Maintenance (SB501000) where you can view or edit the full container record. The **ETA** column is especially useful for spotting delayed shipments at a glance.

### SO Containers (SB401010)

This screen shows outbound shipments and which containers they are assigned to. Use it to verify that shipments headed to customers are linked to the correct container. Filter by **Status** to focus on open or shipped items. The **In Container** column tells you at a glance whether a shipment has been packed into a container or is still unassigned.

### Container Events (SB401020)

Container Events gives you a full tracking timeline across all containers. Each row is a single event -- booked, loaded, departed, in transit, arrived, discharged, and so on. Events are sorted newest-first by default, so the latest update is always at the top. Use the **Container** filter to see the history for one specific container, or filter by **Event Code** to find all containers at a particular milestone (for example, all containers currently marked "IN_TRANSIT").

### Freight Forwarders (SB302000)

This is a new master data screen for managing your carrier and freight forwarder contacts. Enter the company name, primary contact, phone, and email. The API Type and API Key fields are optional -- they support automated tracking updates that are coming in Phase 2. Use the toolbar buttons (Add, Save, Delete) to manage forwarder records. Every container references a forwarder from this list, so keep it up to date.

### Custom Classification (SB401030)

This screen shows all stock items alongside their customs and duty classification fields: Fiber Content, Duty Rate, Preferential Tariff, and Freight Class. Use the **Item Class** filter to focus on a specific product category. This is a read-only inquiry view -- to edit the classification values for a particular item, click the row to navigate to the Stock Items screen (IN202500) where you can update those fields directly.

### Container Maintenance (SB501000)

This screen has not changed. It remains the detailed view for creating and editing individual container records. You can set the container number, type, status, carrier, vessel, ports, dates, and link purchase orders. Access it directly from the workspace or by clicking a row in PO Containers (SB401000).

---

## What Is Coming Next

The following features are planned for upcoming phases:

- **Phase 2:** Automated tracking updates via carrier API webhooks (no more manual status entry)
- **Phase 3:** Container Types and Container Destinations master screens, Container Management Preferences, and the PO Container Lines detail view
- **Future:** Container Distributions and Duty/Tariff Adjustment screens

We will send an update when each phase goes live.

---

## Questions?

- **Slack:** Post in the **#container-tracking** channel
- **Email:** Contact Kevin Bibelhausen directly
- **Acumatica Cases:** Submit a case with Class = INTERNAL
