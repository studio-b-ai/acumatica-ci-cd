<%@ Page Language="C#" MasterPageFile="~/MasterPages/FormDetail.master" AutoEventWireup="true" ValidateRequest="false" CodeFile="SB501000.aspx.cs" Inherits="Page_SB_SB501000" Title="Procurement Command Center" %>
<%@ MasterType VirtualPath="~/MasterPages/FormDetail.master" %>
<asp:Content ID="cont1" ContentPlaceHolderID="phDS" Runat="Server">
    <px:PXDataSource ID="ds" runat="server" Visible="True" Width="100%"
        TypeName="StudioB.Containers.ContainerMaint" PrimaryView="Filter">
        <CallbackCommands>
            <px:PXDSCallbackCommand CommitChanges="True" Name="Save" />
            <px:PXDSCallbackCommand Name="Insert" PostData="Self" />
            <px:PXDSCallbackCommand Name="Delete" PostData="Self" />
            <px:PXDSCallbackCommand Name="First" PostData="Self" StartNewGroup="True" />
            <px:PXDSCallbackCommand Name="Last" PostData="Self" />
            <px:PXDSCallbackCommand Name="CreateLandedCost" CommitChanges="True" />
        </CallbackCommands>
    </px:PXDataSource>
</asp:Content>
<asp:Content ID="cont2" ContentPlaceHolderID="phF" Runat="Server">
    <px:PXFormView ID="frmFilter" runat="server" DataSourceID="ds" DataMember="Filter"
        Width="100%" AllowAutoHide="false">
        <Template>
            <px:PXLayoutRule ID="PXLayoutRule1" runat="server" StartRow="True" />
            <px:PXNumberEdit ID="edKPIOpen" runat="server" DataField="KPIOpen" Width="100px" />
            <px:PXNumberEdit ID="edKPIInTransit" runat="server" DataField="KPIInTransit" Width="100px" />
            <px:PXNumberEdit ID="edKPIArrivingThisWeek" runat="server" DataField="KPIArrivingThisWeek" Width="130px" />
            <px:PXNumberEdit ID="edKPICustomsHold" runat="server" DataField="KPICustomsHold" Width="120px" />
        </Template>
    </px:PXFormView>
</asp:Content>
<asp:Content ID="cont3" ContentPlaceHolderID="phG" Runat="Server">
    <px:PXSplitContainer ID="splitMain" runat="server" Orientation="Vertical" SplitterPosition="400">
        <AutoSize Enabled="True" Container="Window" />
        <Template1>
            <px:PXGrid ID="gridContainers" runat="server" DataSourceID="ds"
                Width="100%" SkinID="Inquire" SyncPosition="True"
                AllowPaging="True" AdjustPageSize="Auto" NoteIndicator="False" FilesIndicator="False">
                <Levels>
                    <px:PXGridLevel DataMember="Containers">
                        <Columns>
                            <px:PXGridColumn DataField="ContainerCD" Width="120" />
                            <px:PXGridColumn DataField="Status" Width="100" />
                            <px:PXGridColumn DataField="TransportMode" Width="90" />
                            <px:PXGridColumn DataField="CarrierCode" Width="90" />
                            <px:PXGridColumn DataField="VesselName" Width="120" />
                            <px:PXGridColumn DataField="ETA" Width="90" />
                            <px:PXGridColumn DataField="ATA" Width="90" />
                            <px:PXGridColumn DataField="PortOfDischarge" Width="90" />
                            <px:PXGridColumn DataField="LastEventCode" Width="100" />
                        </Columns>
                    </px:PXGridLevel>
                </Levels>
                <AutoSize Enabled="True" MinHeight="200" />
                <AutoCallBack Command="Refresh" Target="frmDetail" ActiveBehavior="True">
                    <Behavior RepaintControlsIDs="frmDetail,tabDetail" />
                </AutoCallBack>
            </px:PXGrid>
        </Template1>
        <Template2>
            <px:PXFormView ID="frmDetail" runat="server" DataSourceID="ds" DataMember="Container"
                Width="100%" CaptionVisible="False">
                <Template>
                    <px:PXLayoutRule ID="PXLayoutRule3" runat="server" StartColumn="True" LabelsWidth="SM" ControlSize="M" />
                    <px:PXSelector ID="edContainerCD" runat="server" DataField="ContainerCD" Enabled="False" />
                    <px:PXDropDown ID="edStatus" runat="server" DataField="Status" CommitChanges="True" />
                    <px:PXTextEdit ID="edCarrierCode" runat="server" DataField="CarrierCode" />
                    <px:PXDropDown ID="edTransportMode" runat="server" DataField="TransportMode" />
                    <px:PXTextEdit ID="edVesselName" runat="server" DataField="VesselName" />
                    <px:PXTextEdit ID="edBookingRef" runat="server" DataField="BookingRef" />
                    <px:PXTextEdit ID="edBillOfLading" runat="server" DataField="BillOfLading" />
                    <px:PXLayoutRule ID="PXLayoutRule4" runat="server" StartColumn="True" LabelsWidth="SM" ControlSize="M" />
                    <px:PXDateTimeEdit ID="edETD" runat="server" DataField="ETD" />
                    <px:PXDateTimeEdit ID="edETA" runat="server" DataField="ETA" CommitChanges="True" />
                    <px:PXDateTimeEdit ID="edATA" runat="server" DataField="ATA" />
                    <px:PXTextEdit ID="edPortOfLoading" runat="server" DataField="PortOfLoading" />
                    <px:PXTextEdit ID="edPortOfDischarge" runat="server" DataField="PortOfDischarge" />
                    <px:PXTextEdit ID="edContainerType" runat="server" DataField="ContainerType" />
                    <px:PXTextEdit ID="edSealNbr" runat="server" DataField="SealNbr" />
                    <px:PXTextEdit ID="edLandedCostRefNbr" runat="server" DataField="LandedCostRefNbr" />
                    <px:PXTextEdit ID="edLandedCostStatus" runat="server" DataField="LandedCostStatus" />
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
                    <px:PXTabItem Text="PO Links">
                        <Template>
                            <px:PXGrid ID="gridPOLinks" runat="server" DataSourceID="ds" Width="100%" SkinID="Details">
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
                    <px:PXTabItem Text="Costs">
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
                </Items>
            </px:PXTab>
        </Template2>
    </px:PXSplitContainer>
</asp:Content>
