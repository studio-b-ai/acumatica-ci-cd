<%-- ============================================================================
     SOOrderEntryExt.aspx
     Heritage Fabrics / Studio B  ·  Acumatica 2024 R2 (24.208)
     Customization overlay for SO301000 — Sales Order Entry

     PURPOSE
     ───────
     This file is the human-readable ASPX screen overlay for the Break Pricing
     panel on SO301000.  It is NOT a stand-alone page — it is a fragment that
     Acumatica's Customization Engine merges into the live SO301000.aspx at
     publish time via the project.xml page-delta mechanism.

     The panel is inserted ABOVE the tab strip (px:PXTab ID="tab") that contains
     the Document Details grid, using InsertBefore="tab" on the PXSmartPanel.

     CONTROL HIERARCHY
     ─────────────────
       PXSmartPanel  (ID=pnlBreakPricing)          ← outer repaint wrapper
         └─ PXGroupBox  (ID=gbBreakPricing)         ← collapsible "Break Pricing
              ├─ PXFormView  (frmBreakPricingHeader)   for Selected Item" fieldset
              │    └─ PXTextEdit  (edBreakPricingItemDesc)  → ItemDescription
              └─ PXGrid  (gridBreakTiers)            ← read-only tier grid
                   └─ PXGridLevel  (BreakPricingTiers)
                        ├─ PXGridColumn  TierOrder   Tier
                        ├─ PXGridColumn  MinQty      Min Qty
                        ├─ PXGridColumn  MaxQty      Max Qty   (NullText="No Limit")
                        ├─ PXGridColumn  UnitPrice   Unit Price (Format="Currency")
                        └─ PXGridColumn  UOM         UOM

     DATA MEMBERS  (bound to SOOrderEntry_BreakPricing graph extension views)
     ──────────────────────────────────────────────────────────────────────────
       BreakPricingHeader  → PXFilter<SOPricingBreakHeader>   (header label)
       BreakPricingTiers   → PXSelectReadonly<SOPricingBreakTier> (grid rows)

     RELATED FILES
     ─────────────
       Code/DAC/SOPricingBreakHeader.cs   — header label DAC  (unbound/filter)
       Code/DAC/SOPricingBreakTier.cs     — tier grid DAC     (PXVirtual)
       Code/Graph/SOOrderEntry_BreakPricing.cs — graph extension (populates both)
       PricingBreakPanel.xml              — customization project metadata
============================================================================ --%>
<%@ Page Language="C#" MasterPageFile="~/MasterPages/FormDetail.master"
    AutoEventWireup="true" ValidateRequest="false"
    CodeFile="SO301000.aspx.cs" Inherits="Page_SO301000"
    Title="Untitled Page" %>

<%@ MasterType VirtualPath="~/MasterPages/FormDetail.master" %>

<asp:Content ID="cont1" ContentPlaceHolderID="phDS" runat="Server">
    <%-- Data source is inherited from the base SO301000.aspx page.
         The PXDataSource (ID="ds") defined there serves all controls below. --%>
</asp:Content>

<asp:Content ID="cont2" ContentPlaceHolderID="phF" runat="Server">
    <%-- ═══════════════════════════════════════════════════════════════════════
         BREAK PRICING PANEL
         Positioned ABOVE the Document Details tab strip.
         The Customization Engine's InsertBefore="tab" directive ensures this
         panel renders between the order header FormView and the PXTab that
         contains line items, surviving any future page-level Acumatica upgrades.
    ════════════════════════════════════════════════════════════════════════ --%>

    <%-- ── 1. Outer smart panel ─────────────────────────────────────────────
         Key="BreakPricingHeader" binds the repaint scope to the header view,
         so the panel refreshes automatically when BreakPricingHeader.Current
         changes (i.e. when the user selects a different SOLine row).
         AutoRepaint="True" enables the automatic re-render cycle.
    --%>
    <px:PXSmartPanel ID="pnlBreakPricing"
        runat="server"
        Key="BreakPricingHeader"
        AutoRepaint="True"
        ContentLayout-SpacingSize="None"
        style="margin-bottom: 6px; width: 100%;">

        <%-- ── 2. Collapsible GroupBox ──────────────────────────────────────
             Caption     : "Break Pricing for Selected Item"
             RenderStyle : Fieldset  → renders as a bordered fieldset element
             CollapsibleBehavior : ServerSide  → collapse posts back, preserving
                                                 state across navigation
             InitialExpandState  : Expanded    → defaults open for visibility

             DataMember / DataSourceID give the GroupBox access to the
             BreakPricingHeader view so it can show the item description
             in the panel sub-heading when rendered in Fieldset style.
        --%>
        <px:PXGroupBox ID="gbBreakPricing"
            runat="server"
            Caption="Break Pricing for Selected Item"
            DataMember="BreakPricingHeader"
            DataSourceID="ds"
            RenderStyle="Fieldset"
            CollapsibleBehavior="ServerSide"
            InitialExpandState="Expanded"
            ScreenID="SO301000"
            style="margin: 0 0 6px 0; width: 100%;">

            <Template>

                <%-- ── 3. Header FormView ─────────────────────────────────────
                     Displays the currently-selected inventory item as a
                     read-only label: "{InventoryCD} – {Description}"
                     The value is computed by SOOrderEntry_BreakPricing and
                     stored in SOPricingBreakHeader.ItemDescription.

                     SkinID="Transparent" removes the default FormView border
                     so the label blends into the GroupBox fieldset.
                     TabIndex starts at 1800 to avoid colliding with standard
                     SO301000 controls (which use lower tab indices).
                --%>
                <px:PXFormView ID="frmBreakPricingHeader"
                    runat="server"
                    DataMember="BreakPricingHeader"
                    DataSourceID="ds"
                    SkinID="Transparent"
                    TabIndex="1800">
                    <Template>
                        <px:PXLayoutRule
                            runat="server"
                            StartColumn="True"
                            LabelsWidth="S"
                            ControlSize="XL" />

                        <%-- Bound to SOPricingBreakHeader.ItemDescription --%>
                        <px:PXTextEdit
                            ID="edBreakPricingItemDesc"
                            runat="server"
                            DataField="ItemDescription"
                            LabelID="lblBreakPricingItemDesc"
                            LabelWidth="120px"
                            Size="XL"
                            Enabled="False"
                            SuppressLabel="False">
                            <%-- Refresh the grid whenever the header label changes --%>
                            <AutoCallBack Target="gridBreakTiers" Command="Refresh" />
                        </px:PXTextEdit>
                    </Template>
                </px:PXFormView>

                <%-- ── 4. Break-Tier Grid ──────────────────────────────────────
                     Displays the SOPricingBreakTier rows populated by
                     SOOrderEntry_BreakPricing.breakPricingTiers() delegate.

                     Mode settings:
                       AllowAddNew="False"   — display-only; no inline adds
                       AllowDelete="False"   — display-only; no row deletion
                       AllowUpdate="False"   — fully read-only

                     SkinID="ShortList" renders a compact, borderless grid
                     appropriate for an embedded reference panel.

                     AdjustPageSize="Auto" ensures all rows are visible without
                     paging — break-price ladders rarely exceed 6–8 tiers.

                     NoteIndicator and FilesIndicator are disabled because
                     SOPricingBreakTier is a virtual (unbound) DAC and does
                     not have corresponding NoteID / FileID fields.
                --%>
                <px:PXGrid ID="gridBreakTiers"
                    runat="server"
                    DataMember="BreakPricingTiers"
                    DataSourceID="ds"
                    SkinID="ShortList"
                    Height="120px"
                    Width="100%"
                    AllowPaging="False"
                    AdjustPageSize="Auto"
                    NoteIndicator="False"
                    FilesIndicator="False"
                    TabIndex="1810">

                    <AutoSize Enabled="False" />

                    <%-- Fully read-only mode --%>
                    <Mode
                        AllowAddNew="False"
                        AllowDelete="False"
                        AllowUpdate="False" />

                    <Levels>
                        <px:PXGridLevel DataMember="BreakPricingTiers">
                            <Columns>

                                <%-- Col 1: Tier (1-based display sequence) --%>
                                <px:PXGridColumn
                                    DataField="TierOrder"
                                    Width="50px"
                                    TextAlign="Center"
                                    HeaderText="Tier" />

                                <%-- Col 2: Min Qty (break lower bound, inclusive) --%>
                                <px:PXGridColumn
                                    DataField="MinQty"
                                    Width="80px"
                                    TextAlign="Right"
                                    HeaderText="Min Qty" />

                                <%-- Col 3: Max Qty (break upper bound, exclusive)
                                     NullText="No Limit" renders for the final tier
                                     whose MaxQty the graph extension leaves as null. --%>
                                <px:PXGridColumn
                                    DataField="MaxQty"
                                    Width="80px"
                                    TextAlign="Right"
                                    HeaderText="Max Qty"
                                    NullText="No Limit" />

                                <%-- Col 4: Unit Price — currency-formatted decimal
                                     Format="Currency" applies the tenant's functional
                                     currency symbol and decimal convention. --%>
                                <px:PXGridColumn
                                    DataField="UnitPrice"
                                    Width="90px"
                                    TextAlign="Right"
                                    HeaderText="Unit Price"
                                    Format="Currency" />

                                <%-- Col 5: UOM (e.g. YD, EA, M) --%>
                                <px:PXGridColumn
                                    DataField="UOM"
                                    Width="60px"
                                    HeaderText="UOM" />

                            </Columns>
                        </px:PXGridLevel>
                    </Levels>

                    <%-- Empty action bar — no toolbar buttons needed for a read-only
                         reference panel.  DefaultAction="" prevents accidental double-
                         click row navigation. --%>
                    <ActionBar Position="Top" DefaultAction="">
                        <CustomItems />
                    </ActionBar>

                </px:PXGrid>

            </Template>
        </px:PXGroupBox>

    </px:PXSmartPanel>
    <%-- ══ End Break Pricing Panel ══════════════════════════════════════════ --%>

</asp:Content>
