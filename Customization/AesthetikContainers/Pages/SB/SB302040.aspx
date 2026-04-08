<%@ Page Language="C#" MasterPageFile="~/MasterPages/FormView.master" AutoEventWireup="true" ValidateRequest="false" CodeFile="SB302040.aspx.cs" Inherits="Page_SB_SB302040" Title="Customs Brokers" %>
<%@ MasterType VirtualPath="~/MasterPages/FormView.master" %>
<asp:Content ID="cont1" ContentPlaceHolderID="phDS" Runat="Server">
    <px:PXDataSource ID="ds" runat="server" Visible="True" Width="100%"
        TypeName="StudioB.Containers.CustomsBrokerMaint" PrimaryView="Broker">
        <CallbackCommands>
            <px:PXDSCallbackCommand Name="Insert" PostData="Self" />
            <px:PXDSCallbackCommand CommitChanges="True" Name="Save" />
            <px:PXDSCallbackCommand Name="Delete" PostData="Self" />
            <px:PXDSCallbackCommand Name="First" PostData="Self" StartNewGroup="True" />
            <px:PXDSCallbackCommand Name="Last" PostData="Self" />
        </CallbackCommands>
    </px:PXDataSource>
</asp:Content>
<asp:Content ID="cont2" ContentPlaceHolderID="phF" Runat="Server">
    <px:PXFormView ID="form" runat="server" DataSourceID="ds" DataMember="Broker" Width="100%">
        <Template>
            <px:PXLayoutRule ID="PXLayoutRule1" runat="server" StartColumn="True" LabelsWidth="M" ControlSize="XM" />
            <px:PXSelector ID="edBrokerCD" runat="server" DataField="BrokerCD" />
            <px:PXTextEdit ID="edDescription" runat="server" DataField="Description" />
            <px:PXTextEdit ID="edFilerCode" runat="server" DataField="FilerCode" />
            <px:PXCheckBox ID="chkActive" runat="server" DataField="Active" />
            <px:PXLayoutRule ID="PXLayoutRule2" runat="server" StartColumn="True" LabelsWidth="M" ControlSize="XM" />
            <px:PXTextEdit ID="edContactName" runat="server" DataField="ContactName" />
            <px:PXMailEdit ID="edEmail" runat="server" DataField="Email" />
            <px:PXMaskEdit ID="edPhone" runat="server" DataField="Phone" />
            <px:PXLayoutRule ID="PXLayoutRule3" runat="server" StartRow="True" LabelsWidth="M" ControlSize="XXL" />
            <px:PXTextEdit ID="edNotes" runat="server" DataField="Notes" />
        </Template>
    </px:PXFormView>
</asp:Content>
