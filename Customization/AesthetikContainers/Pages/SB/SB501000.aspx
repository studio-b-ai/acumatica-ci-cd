<%@ Page Language="C#" MasterPageFile="~/MasterPages/FormDetail.master" AutoEventWireup="true" ValidateRequest="false" CodeFile="SB501000.aspx.cs" Inherits="Page_SB_SB501000" Title="Procurement Command Center" %>
<%@ MasterType VirtualPath="~/MasterPages/FormDetail.master" %>
<asp:Content ID="cont1" ContentPlaceHolderID="phDS" Runat="Server">
    <px:PXDataSource ID="ds" runat="server" Visible="True" Width="100%"
        TypeName="StudioB.Containers.ContainerMaint" PrimaryView="Filter">
        <CallbackCommands>
            <px:PXDSCallbackCommand CommitChanges="True" Name="Save" />
            <px:PXDSCallbackCommand Name="SaveChanges" CommitChanges="True" />
            <px:PXDSCallbackCommand Name="Insert" PostData="Self" />
            <px:PXDSCallbackCommand Name="Delete" PostData="Self" />
            <px:PXDSCallbackCommand Name="First" PostData="Self" StartNewGroup="True" />
            <px:PXDSCallbackCommand Name="Last" PostData="Self" />
            <%-- CreateLandedCost removed — auto LC on receipt release --%>
            <%-- 2026-04-08: Phase E + F — new Command Center actions --%>
            <px:PXDSCallbackCommand Name="MarkCustomsCleared" CommitChanges="True" StartNewGroup="True" />
            <px:PXDSCallbackCommand Name="MarkDelivered" CommitChanges="True" />
            <px:PXDSCallbackCommand Name="ReceiveGoods" CommitChanges="True" />
            <px:PXDSCallbackCommand Name="AddPOLink" CommitChanges="True" Visible="False" />
            <px:PXDSCallbackCommand Name="RemovePOLink" CommitChanges="True" Visible="False" />
            <px:PXDSCallbackCommand Name="AttachDocument" CommitChanges="True" Visible="False" />
            <px:PXDSCallbackCommand Name="RecordETAUpdate" CommitChanges="True" Visible="False" />
            <%-- PlanNextOrder removed — future DRP integration --%>
            <px:PXDSCallbackCommand Name="ImportForwarderCSV" CommitChanges="True" StartNewGroup="True" />
            <px:PXDSCallbackCommand Name="OpenContainerDetail" CommitChanges="True" Visible="False" />
        </CallbackCommands>
    </px:PXDataSource>
</asp:Content>
<asp:Content ID="cont2" ContentPlaceHolderID="phF" Runat="Server">
    <px:PXFormView ID="frmFilter" runat="server" DataSourceID="ds" DataMember="Filter"
        Width="100%" AllowAutoHide="false" CaptionVisible="False" RenderStyle="Simple"
        SkinID="Transparent">
        <Template>
            <px:PXLayoutRule ID="PXLayoutRule1" runat="server" StartRow="True" />
            <px:PXHtmlView ID="htmlKPITiles" runat="server" DataField="KPITilesHtml"
                Height="280px" Width="100%" SkinID="Label" />
            <px:PXDropDown ID="edViewMode" runat="server" DataField="ViewMode"
                CommitChanges="True" Style="display:none;" />
        </Template>
    </px:PXFormView>
    <%-- Timeline Command Bar — updates on grid row click --%>
    <px:PXFormView ID="frmTimeline" runat="server" DataSourceID="ds" DataMember="Container"
        Width="100%" CaptionVisible="False" RenderStyle="Simple" SkinID="Transparent">
        <Template>
            <px:PXLayoutRule runat="server" StartRow="True" />
            <px:PXHtmlView ID="htmlTimeline" runat="server" DataField="TimelineHtml"
                Height="90px" Width="100%" SkinID="Label" />
            <px:PXTextEdit ID="edTabLabelsJson" runat="server" DataField="TabLabelsJson"
                SuppressLabel="True" Style="display:none;" />
        </Template>
    </px:PXFormView>
</asp:Content>
<asp:Content ID="cont3" ContentPlaceHolderID="phG" Runat="Server">
    <%-- Full-width container grid --%>
    <px:PXGrid ID="gridContainers" runat="server" DataSourceID="ds"
        Width="100%" SkinID="DetailsInTab" SyncPosition="True"
        AllowPaging="True" AdjustPageSize="Auto" AllowInsert="True" AllowDelete="True"
        NoteIndicator="True" FilesIndicator="True">
        <Levels>
            <px:PXGridLevel DataMember="Containers">
                <Columns>
                    <px:PXGridColumn DataField="RiskLevel" Width="30" TextAlign="Center" />
                    <px:PXGridColumn DataField="ContainerCD" Width="120" LinkCommand="OpenContainerDetail" />
                    <px:PXGridColumn DataField="Status" Width="110" />
                    <px:PXGridColumn DataField="TransportMode" Width="70" />
                    <px:PXGridColumn DataField="CarrierCode" Width="80" />
                    <px:PXGridColumn DataField="VesselName" Width="120" />
                    <px:PXGridColumn DataField="ETA" Width="90" />
                    <px:PXGridColumn DataField="ATA" Width="90" />
                    <px:PXGridColumn DataField="LastFreeDay" Width="90" />
                    <px:PXGridColumn DataField="DaysToLFD" Width="60" TextAlign="Right" />
                    <px:PXGridColumn DataField="DemurrageExposure" Width="100" TextAlign="Right" />
                    <px:PXGridColumn DataField="FactoryPromisedDate" Width="90" />
                    <px:PXGridColumn DataField="FactoryActualDate" Width="90" />
                    <px:PXGridColumn DataField="MillAckDate" Width="90" />
                    <px:PXGridColumn DataField="DocsSummary" Width="60" TextAlign="Center" />
                    <px:PXGridColumn DataField="PortOfDischarge" Width="90" />
                    <px:PXGridColumn DataField="LastEventCode" Width="100" />
                </Columns>
            </px:PXGridLevel>
        </Levels>
        <AutoSize Enabled="True" MinHeight="300" Container="Window" />
        <AutoCallBack Command="Refresh" Target="frmTimeline" ActiveBehavior="True">
            <Behavior RepaintControlsIDs="frmTimeline" CommitChanges="True" />
        </AutoCallBack>
    </px:PXGrid>

    <%-- Slide-out detail panel (right-anchored) --%>
    <px:PXSmartPanel ID="pnlContainerDetail" runat="server"
        Caption="Container Detail" CaptionVisible="True"
        LoadOnDemand="True" Key="Container" AutoCallBack-Enabled="True"
        AutoCallBack-Target="frmDetail" AutoCallBack-ActiveBehavior="True"
        AutoRepaint="True"
        ShowCloseButton="True" Width="600px" Height="100%"
        Style="overflow-y:auto;">

        <px:PXFormView ID="frmDetail" runat="server" DataSourceID="ds" DataMember="Container"
            Width="100%" CaptionVisible="False">
            <Template>
                <%-- Group 1: Identity --%>
                <px:PXLayoutRule ID="lrIdentity" runat="server" StartColumn="True"
                    StartGroup="True" GroupCaption="Identity" LabelsWidth="SM" ControlSize="M" />
                <px:PXSelector ID="edContainerCD" runat="server" DataField="ContainerCD" Enabled="False" />
                <px:PXDropDown ID="edStatus" runat="server" DataField="Status" CommitChanges="True" />
                <px:PXTextEdit ID="edCarrierCode" runat="server" DataField="CarrierCode" />
                <px:PXDropDown ID="edTransportMode" runat="server" DataField="TransportMode" />
                <px:PXTextEdit ID="edVesselName" runat="server" DataField="VesselName" />
                <px:PXTextEdit ID="edSealNbr" runat="server" DataField="SealNbr" />

                <%-- Group 2: Booking & Docs --%>
                <px:PXLayoutRule ID="lrBooking" runat="server"
                    StartGroup="True" GroupCaption="Booking &amp; Docs" LabelsWidth="SM" ControlSize="M" />
                <px:PXTextEdit ID="edBookingRef" runat="server" DataField="BookingRef" />
                <px:PXTextEdit ID="edBillOfLading" runat="server" DataField="BillOfLading" />
                <px:PXTextEdit ID="edContainerType" runat="server" DataField="ContainerType" />
                <px:PXSelector ID="edFreightForwarderID" runat="server" DataField="FreightForwarderID" />
                <px:PXSelector ID="edBrokerID" runat="server" DataField="BrokerID" />
                <px:PXTextEdit ID="edLandedCostRefNbr" runat="server" DataField="LandedCostRefNbr" />
                <px:PXTextEdit ID="edLandedCostStatus" runat="server" DataField="LandedCostStatus" />

                <%-- Group 3: Dates (consolidated) --%>
                <px:PXLayoutRule ID="lrDates" runat="server"
                    StartGroup="True" GroupCaption="Dates" LabelsWidth="SM" ControlSize="M" />
                <px:PXDateTimeEdit ID="edETD" runat="server" DataField="ETD" />
                <px:PXDateTimeEdit ID="edETA" runat="server" DataField="ETA" CommitChanges="True" />
                <px:PXDateTimeEdit ID="edATA" runat="server" DataField="ATA" />
                <px:PXDateTimeEdit ID="edLastFreeDay" runat="server" DataField="LastFreeDay" />
                <px:PXNumberEdit ID="edDemurrageDailyRate" runat="server" DataField="DemurrageDailyRate" />
                <px:PXDateTimeEdit ID="edMillAckDate" runat="server" DataField="MillAckDate" />
                <px:PXDateTimeEdit ID="edFactoryPromisedDate" runat="server" DataField="FactoryPromisedDate" />
                <px:PXDateTimeEdit ID="edFactoryActualDate" runat="server" DataField="FactoryActualDate" />
                <px:PXDateTimeEdit ID="edCargoReadyDate" runat="server" DataField="CargoReadyDate" />
                <px:PXDateTimeEdit ID="edOnBoardDate" runat="server" DataField="OnBoardDate" />
                <px:PXDateTimeEdit ID="edDrayageAppointmentDate" runat="server" DataField="DrayageAppointmentDate" />
                <px:PXTextEdit ID="edDeliveryOrderNbr" runat="server" DataField="DeliveryOrderNbr" />
                <px:PXDateTimeEdit ID="edDeliveryOrderDate" runat="server" DataField="DeliveryOrderDate" />
                <px:PXDateTimeEdit ID="edPaymentDueDate" runat="server" DataField="PaymentDueDate" />
                <px:PXNumberEdit ID="edEstimatedFreight" runat="server" DataField="EstimatedFreight" />
                <px:PXTextEdit ID="edSCACNumber" runat="server" DataField="SCACNumber" />
                <px:PXTextEdit ID="edBrokerInvoiceNbr" runat="server" DataField="BrokerInvoiceNbr" />
            </Template>
        </px:PXFormView>
        <px:PXTab ID="tabDetail" runat="server" Width="100%" DataSourceID="ds">
            <Items>
                <px:PXTabItem Text="Events">
                    <Template>
                        <px:PXGrid ID="gridEvents" runat="server" DataSourceID="ds" Width="100%" SkinID="Details">
                            <Levels>
                                <px:PXGridLevel DataMember="Events">
                                    <Columns>
                                        <px:PXGridColumn DataField="EventDateTime" Width="130" />
                                        <px:PXGridColumn DataField="NormalizedEventCode" Width="120" />
                                        <px:PXGridColumn DataField="Description" Width="250" />
                                        <px:PXGridColumn DataField="LocationName" Width="150" />
                                    </Columns>
                                </px:PXGridLevel>
                            </Levels>
                            <AutoSize Enabled="True" MinHeight="150" />
                        </px:PXGrid>
                    </Template>
                </px:PXTabItem>
                <px:PXTabItem Text="PO Links" RepaintOnDemand="False">
                    <Template>
                        <px:PXGrid ID="gridPOLinks" runat="server" DataSourceID="ds" Width="100%" SkinID="Details">
                            <ActionBar>
                                <CustomItems>
                                    <px:PXToolBarButton Text="Add PO Line" CommandName="AddPOLink" CommandSourceID="ds" />
                                    <px:PXToolBarButton Text="Remove PO Line" CommandName="RemovePOLink" CommandSourceID="ds" />
                                </CustomItems>
                            </ActionBar>
                            <Levels>
                                <px:PXGridLevel DataMember="POLinks">
                                    <Columns>
                                        <px:PXGridColumn DataField="OrderType" Width="60" />
                                        <px:PXGridColumn DataField="OrderNbr" Width="90" />
                                        <px:PXGridColumn DataField="BAccount__AcctName" Width="140" />
                                        <px:PXGridColumn DataField="LineNbr" Width="50" />
                                        <px:PXGridColumn DataField="InventoryItem__InventoryCD" Width="120" />
                                        <px:PXGridColumn DataField="InventoryItem__Descr" Width="180" />
                                        <px:PXGridColumn DataField="POLine__OrderQty" Width="80" />
                                        <px:PXGridColumn DataField="POLine__UOM" Width="60" />
                                    </Columns>
                                </px:PXGridLevel>
                            </Levels>
                            <AutoSize Enabled="True" MinHeight="150" />
                        </px:PXGrid>
                    </Template>
                </px:PXTabItem>
                <px:PXTabItem Text="Costs" RepaintOnDemand="False">
                    <Template>
                        <px:PXGrid ID="gridCosts" runat="server" DataSourceID="ds" Width="100%" SkinID="Details">
                            <Levels>
                                <px:PXGridLevel DataMember="Costs">
                                    <Columns>
                                        <px:PXGridColumn DataField="CostType" Width="100" CommitChanges="True" />
                                        <px:PXGridColumn DataField="Description" Width="180" />
                                        <px:PXGridColumn DataField="Amount" Width="100" />
                                        <px:PXGridColumn DataField="VendorID" Width="140" CommitChanges="True" />
                                        <px:PXGridColumn DataField="ReferenceNbr" Width="120" />
                                        <px:PXGridColumn DataField="APDocType" Width="80" CommitChanges="True" />
                                        <px:PXGridColumn DataField="APRefNbr" Width="110" CommitChanges="True" />
                                    </Columns>
                                </px:PXGridLevel>
                            </Levels>
                            <AutoSize Enabled="True" MinHeight="150" />
                        </px:PXGrid>
                    </Template>
                </px:PXTabItem>
                <px:PXTabItem Text="Documents" RepaintOnDemand="False">
                    <Template>
                        <px:PXGrid ID="gridDocuments" runat="server" DataSourceID="ds" Width="100%" SkinID="Details">
                            <ActionBar>
                                <CustomItems>
                                    <px:PXToolBarButton Text="Attach Document" CommandName="AttachDocument" CommandSourceID="ds" />
                                </CustomItems>
                            </ActionBar>
                            <Levels>
                                <px:PXGridLevel DataMember="Documents">
                                    <Columns>
                                        <px:PXGridColumn DataField="DocumentType" Width="180" CommitChanges="True" />
                                        <px:PXGridColumn DataField="Required" Width="80" Type="CheckBox" />
                                        <px:PXGridColumn DataField="Status" Width="100" CommitChanges="True" />
                                        <px:PXGridColumn DataField="ReceivedDate" Width="110" />
                                        <px:PXGridColumn DataField="Note" Width="240" />
                                    </Columns>
                                </px:PXGridLevel>
                            </Levels>
                            <AutoSize Enabled="True" MinHeight="150" />
                        </px:PXGrid>
                    </Template>
                </px:PXTabItem>
                <px:PXTabItem Text="ETA History" RepaintOnDemand="False">
                    <Template>
                        <px:PXGrid ID="gridETAHistory" runat="server" DataSourceID="ds" Width="100%" SkinID="Details">
                            <ActionBar>
                                <CustomItems>
                                    <px:PXToolBarButton Text="Snapshot Current ETA" CommandName="RecordETAUpdate" CommandSourceID="ds" />
                                </CustomItems>
                            </ActionBar>
                            <Levels>
                                <px:PXGridLevel DataMember="ETAHistory">
                                    <Columns>
                                        <px:PXGridColumn DataField="RecordedDate" Width="130" />
                                        <px:PXGridColumn DataField="PreviousETA" Width="110" />
                                        <px:PXGridColumn DataField="NewETA" Width="110" />
                                        <px:PXGridColumn DataField="Source" Width="100" />
                                        <px:PXGridColumn DataField="Note" Width="260" />
                                    </Columns>
                                </px:PXGridLevel>
                            </Levels>
                            <AutoSize Enabled="True" MinHeight="150" />
                        </px:PXGrid>
                    </Template>
                </px:PXTabItem>
                <px:PXTabItem Text="Lead Time" RepaintOnDemand="False">
                    <Template>
                        <px:PXGrid ID="gridLeadTimes" runat="server" DataSourceID="ds"
                            Width="100%" SkinID="Details">
                            <Levels>
                                <px:PXGridLevel DataMember="LeadTimes">
                                    <Columns>
                                        <px:PXGridColumn DataField="OrderNbr" Width="100" />
                                        <px:PXGridColumn DataField="VendorName" Width="120" />
                                        <px:PXGridColumn DataField="InventoryCD" Width="120" />
                                        <px:PXGridColumn DataField="PlacedToAcked" Width="80" TextAlign="Right" />
                                        <px:PXGridColumn DataField="AckedToFactory" Width="80" TextAlign="Right" />
                                        <px:PXGridColumn DataField="FactoryToShip" Width="80" TextAlign="Right" />
                                        <px:PXGridColumn DataField="ShipToDeliver" Width="80" TextAlign="Right" />
                                        <px:PXGridColumn DataField="TotalDays" Width="60" TextAlign="Right" />
                                    </Columns>
                                </px:PXGridLevel>
                            </Levels>
                            <AutoSize Enabled="True" MinHeight="150" />
                        </px:PXGrid>
                    </Template>
                </px:PXTabItem>
            </Items>
        </px:PXTab>
    </px:PXSmartPanel>

    <%-- Add PO Line smart panel --%>
    <px:PXSmartPanel ID="pnlAddPOLine" runat="server" Style="z-index: 100;"
        Caption="Add PO Line to Container" CaptionVisible="True"
        LoadOnDemand="True" Key="AddPOLineFilter" AutoCallBack-Enabled="True"
        AutoCallBack-Target="frmAddPOLineFilter"
        AutoCallBack-ActiveBehavior="True" AcceptButtonID="btnAddPOLineOK" Width="420px">
        <px:PXFormView ID="frmAddPOLineFilter" runat="server" DataSourceID="ds"
            Style="z-index: 100" Width="100%" CaptionVisible="False"
            DataMember="AddPOLineFilter" SkinID="Transparent">
            <Template>
                <px:PXLayoutRule ID="pnlLayoutRule1" runat="server" StartColumn="True" LabelsWidth="S" ControlSize="M" />
                <px:PXSelector ID="edPnlVendorID" runat="server" DataField="VendorID" CommitChanges="True" />
                <px:PXSelector ID="edPnlOrderNbr" runat="server" DataField="OrderNbr" CommitChanges="True" />
                <px:PXSelector ID="edPnlLineNbr" runat="server" DataField="LineNbr" CommitChanges="True" />
            </Template>
        </px:PXFormView>
        <div style="padding:8px; text-align:right;">
            <px:PXButton ID="btnAddPOLineOK" runat="server" DialogResult="OK" Text="Add" />
            <px:PXButton ID="btnAddPOLineCancel" runat="server" DialogResult="Cancel" Text="Cancel" />
        </div>
    </px:PXSmartPanel>
</asp:Content>
