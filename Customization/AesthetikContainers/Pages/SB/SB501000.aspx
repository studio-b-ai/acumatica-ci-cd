<%@ Page Language="C#" MasterPageFile="~/MasterPages/FormDetail.master" AutoEventWireup="true" ValidateRequest="false" Title="Container Maintenance" %>
<%@ MasterType VirtualPath="~/MasterPages/FormDetail.master" %>
<asp:Content ID="cont1" ContentPlaceHolderID="phDS" Runat="Server">
    <px:PXDataSource ID="ds" runat="server" Visible="True" Width="100%"
        TypeName="StudioB.Containers.ContainerMaint" PrimaryView="Container">
        <CallbackCommands>
            <px:PXDSCallbackCommand Name="Insert" PostData="Self" />
            <px:PXDSCallbackCommand CommitChanges="True" Name="Save" />
            <px:PXDSCallbackCommand Name="First" PostData="Self" StartNewGroup="True" />
            <px:PXDSCallbackCommand Name="Last" PostData="Self" />
        </CallbackCommands>
    </px:PXDataSource>
</asp:Content>
<asp:Content ID="cont2" ContentPlaceHolderID="phF" Runat="Server">
    <px:PXFormView ID="form" runat="server" DataSourceID="ds" DataMember="Container" Width="100%">
        <Template>
            <px:PXLayoutRule ID="PXLayoutRule1" runat="server" StartColumn="True" LabelsWidth="SM" ControlSize="M" />
            <px:PXSelector ID="edContainerCD" runat="server" DataField="ContainerCD" />
            <px:PXDropDown ID="edStatus" runat="server" DataField="Status" />
            <px:PXTextEdit ID="edCarrierCode" runat="server" DataField="CarrierCode" />
            <px:PXTextEdit ID="edVesselName" runat="server" DataField="VesselName" />
            <px:PXLayoutRule ID="PXLayoutRule2" runat="server" StartColumn="True" LabelsWidth="SM" ControlSize="M" />
            <px:PXDateTimeEdit ID="edETD" runat="server" DataField="ETD" />
            <px:PXDateTimeEdit ID="edETA" runat="server" DataField="ETA" />
            <px:PXDateTimeEdit ID="edATA" runat="server" DataField="ATA" />
            <px:PXTextEdit ID="edPortOfLoading" runat="server" DataField="PortOfLoading" />
            <px:PXTextEdit ID="edPortOfDischarge" runat="server" DataField="PortOfDischarge" />
        </Template>
    </px:PXFormView>
</asp:Content>
<asp:Content ID="cont3" ContentPlaceHolderID="phG" Runat="Server">
    <px:PXTab ID="tab" runat="server" Width="100%">
        <Items>
            <px:PXTabItem Text="Events">
                <Template>
                    <px:PXGrid ID="gridEvents" runat="server" DataSourceID="ds" Width="100%" SkinID="Details">
                        <Levels>
                            <px:PXGridLevel DataMember="ContainerEvents">
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
                            <px:PXGridLevel DataMember="ContainerPOLinks">
                                <Columns>
                                    <px:PXGridColumn DataField="OrderType" Width="70" />
                                    <px:PXGridColumn DataField="OrderNbr" Width="100" />
                                    <px:PXGridColumn DataField="LineNbr" Width="70" />
                                </Columns>
                            </px:PXGridLevel>
                        </Levels>
                        <AutoSize Enabled="True" MinHeight="150" />
                    </px:PXGrid>
                </Template>
            </px:PXTabItem>
        </Items>
        <AutoSize Container="Window" Enabled="True" MinHeight="180" />
    </px:PXTab>
</asp:Content>
