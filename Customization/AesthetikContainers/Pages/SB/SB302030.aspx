<%@ Page Language="C#" MasterPageFile="~/MasterPages/FormView.master" AutoEventWireup="true" ValidateRequest="false" CodeFile="SB302030.aspx.cs" Inherits="Page_SB_SB302030" Title="Container Preferences" %>
<%@ MasterType VirtualPath="~/MasterPages/FormView.master" %>
<asp:Content ID="cont1" ContentPlaceHolderID="phDS" Runat="Server">
    <px:PXDataSource ID="ds" runat="server" Visible="True" Width="100%"
        TypeName="StudioB.Containers.ContainerPrefsMaint" PrimaryView="Prefs">
        <CallbackCommands>
            <px:PXDSCallbackCommand CommitChanges="True" Name="Save" />
        </CallbackCommands>
    </px:PXDataSource>
</asp:Content>
<asp:Content ID="cont2" ContentPlaceHolderID="phF" Runat="Server">
    <px:PXFormView ID="form" runat="server" DataSourceID="ds" DataMember="Prefs" Width="100%">
        <Template>
            <px:PXLayoutRule ID="PXLayoutRule1" runat="server" StartColumn="True" LabelsWidth="SM" ControlSize="M" />
            <px:PXTextEdit ID="edDefaultCarrierCode" runat="server" DataField="DefaultCarrierCode" />
            <px:PXSelector ID="edDefaultContainerType" runat="server" DataField="DefaultContainerType" />
            <px:PXTextEdit ID="edDefaultInTransitWarehouse" runat="server" DataField="DefaultInTransitWarehouse" />
            <px:PXCheckBox ID="chkAutoLinkPOsByRef" runat="server" DataField="AutoLinkPOsByRef" />
            <px:PXNumberEdit ID="edTrackingPollIntervalHours" runat="server" DataField="TrackingPollIntervalHours" />
        </Template>
    </px:PXFormView>
</asp:Content>
