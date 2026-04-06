# Procurement Command Center — Design

**Date:** 2026-04-05
**Status:** Approved
**Screen:** SB501000 (replaces existing Container Maintenance)

## Goal

Replace the broken single-record Container Maintenance screen with a command center layout: KPI cards at top, container grid on left, editable detail panel on right. Fixes the TabView.master crash and upgrades the screen in one deploy.

## Layout

```
┌─────────────────────────────────────────────────────────────┐
│  phF: ContainerFilter                                        │
│  [Open: 12]  [In Transit: 8]  [This Week: 3]  [⚠ Hold: 2]  │
├─────────────────────────────┬───────────────────────────────┤
│  phG: PXSplitContainer      │                               │
│                              │                               │
│  PXGrid "Containers"        │  PXFormView "Containers"      │
│  (list, SyncPosition=True)  │  (current row, editable)      │
│                              │  ─────────────────           │
│  ContainerCD | Status | ETA │  PXTab:                       │
│  MAEU1234    | TRANSIT | 4/8│    Events (read-only grid)    │
│  CGMU5678    | HOLD    | 4/3│    PO Links (grid)            │
│  ...                         │                               │
└─────────────────────────────┴───────────────────────────────┘
```

## Master Page

`FormDetail.master` — provides phDS, phF, phG content placeholders.

## KPI Cards

Four clickable cards in the filter form. Each shows a count and acts as a toggle filter:

| Card | Filter Logic | Highlight |
|------|-------------|-----------|
| Open | Status IN (BOOKED, DEPARTED) | Default |
| In Transit | Status = IN_TRANSIT | Default |
| Arriving This Week | ETA >= Monday AND ETA < next Monday | Default |
| Customs Hold | Status = CUSTOMS_HOLD | Red when count > 0 |

Click a card → sets `ActiveFilter` on `ContainerFilter` → refreshes grid to that subset.
Click again (same card) → clears filter → shows all.

## DACs

### ContainerFilter (new, unbound)

```csharp
[Serializable]
[PXVirtual]
public class ContainerFilter : IBqlTable
{
    // KPI counts (computed in delegate, read-only)
    [PXInt] [PXUIField(DisplayName = "Open")]
    public int? OpenCount { get; set; }

    [PXInt] [PXUIField(DisplayName = "In Transit")]
    public int? InTransitCount { get; set; }

    [PXInt] [PXUIField(DisplayName = "Arriving This Week")]
    public int? ArrivingThisWeekCount { get; set; }

    [PXInt] [PXUIField(DisplayName = "Customs Hold")]
    public int? CustomsHoldCount { get; set; }

    // Active filter (null = show all)
    [PXString(20)]
    public string ActiveFilter { get; set; }
}
```

### Existing DACs (unchanged)

- `UsrContainer` — master record
- `UsrContainerEvent` — child events
- `UsrContainerPOLink` — child PO links

## Graph

### ContainerMaint (rewritten)

```csharp
public class ContainerMaint : PXGraph<ContainerMaint>
{
    public PXFilter<ContainerFilter> Filter;

    [PXFilterable]
    public SelectFrom<UsrContainer>.OrderBy<UsrContainer.eta.Asc>.View Containers;

    public SelectFrom<UsrContainerEvent>
        .Where<UsrContainerEvent.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
        .OrderBy<UsrContainerEvent.eventDateTime.Desc>.View Events;

    public SelectFrom<UsrContainerPOLink>
        .Where<UsrContainerPOLink.containerID.IsEqual<UsrContainer.containerID.FromCurrent>>
        .View POLinks;
}
```

### Filter Delegate

```csharp
protected virtual IEnumerable containers()
{
    ContainerFilter filter = Filter.Current;

    // Query all containers once
    var all = SelectFrom<UsrContainer>.View.Select(this).FirstTableItems.ToList();

    // Compute KPI counts
    DateTime weekStart = DateTime.Today.AddDays(-(int)DateTime.Today.DayOfWeek + 1);
    DateTime weekEnd = weekStart.AddDays(7);

    filter.OpenCount = all.Count(c => c.Status == "BOOKED" || c.Status == "DEPARTED");
    filter.InTransitCount = all.Count(c => c.Status == "IN_TRANSIT");
    filter.ArrivingThisWeekCount = all.Count(c => c.ETA >= weekStart && c.ETA < weekEnd);
    filter.CustomsHoldCount = all.Count(c => c.Status == "CUSTOMS_HOLD");

    // Apply active filter
    foreach (var c in all)
    {
        bool include = filter.ActiveFilter switch
        {
            "OPEN" => c.Status == "BOOKED" || c.Status == "DEPARTED",
            "TRANSIT" => c.Status == "IN_TRANSIT",
            "THIS_WEEK" => c.ETA >= weekStart && c.ETA < weekEnd,
            "HOLD" => c.Status == "CUSTOMS_HOLD",
            _ => true
        };
        if (include) yield return c;
    }
}
```

### KPI Actions

```csharp
public PXAction<UsrContainer> FilterOpen;
[PXButton] [PXUIField(DisplayName = "Open")]
protected void filterOpen()
{
    var f = Filter.Current;
    f.ActiveFilter = f.ActiveFilter == "OPEN" ? null : "OPEN";
    Containers.View.RequestRefresh();
}
// Same pattern for FilterTransit, FilterThisWeek, FilterHold
```

### Existing Logic (preserved)

- `RefreshTracking` action — manual carrier refresh
- `Persist()` override — propagates ETA to linked POs via `ContainerDatePropagation`
- Webhook POST on save

## File Changes

### C# (compiled into StudioB.Containers.dll)

| File | Action |
|------|--------|
| `ContainerFilter.cs` | Create — new filter DAC |
| `ContainerMaint.cs` | Rewrite — new graph with filter/delegate/actions |

### project.xml (CDATA)

| Element | Action |
|---------|--------|
| `<File AppRelativePath="Pages\SB\SB501000.aspx">` | Replace ASPX content |
| Any inline `<Graph ClassName="ContainerMaint">` CDATA | Remove (DLL handles it) |

### Unchanged

- All other DACs (UsrContainer, UsrContainerEvent, UsrContainerPOLink, UsrContainerType, UsrPort, UsrContainerPrefs)
- All other screens (SB302000-SB302030)
- Extension classes (POOrderEntry_Extension, InventoryAllocDetEnq_Extension)
- ScreenWithRights / SiteMap entries
- Generic Inquiries

## Deployment Risk

The existing ASPX on prod has `TabView.master` (wrong, from feat/command-center branch). The CDATA import may not overwrite it. If the deploy doesn't fix the screen:
1. Delete SB501000.aspx from AesthetikContainers project via SM204505
2. Redeploy — the CDATA will create the file fresh

## Testing

1. Deploy to SaaS sandbox first
2. Navigate to SB501000 — screen loads without error
3. KPI cards show correct counts
4. Click a KPI card — grid filters
5. Click again — filter clears
6. Select a container in grid — detail panel populates
7. Edit a field in detail panel — save works
8. Events and PO Links tabs show correct child records
