<%@ Page Language="C#" MasterPageFile="~/MasterPages/FormView.master" AutoEventWireup="true" ValidateRequest="false" CodeFile="SB302000.aspx.cs" Inherits="Page_SB_SB302000" Title="Freight Forwarders" %>
<%@ MasterType VirtualPath="~/MasterPages/FormView.master" %>
<asp:Content ID="cont1" ContentPlaceHolderID="phDS" Runat="Server">
    <px:PXDataSource ID="ds" runat="server" Visible="True" Width="100%"
        TypeName="StudioB.Containers.FreightForwarderMaint" PrimaryView="Forwarder">
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
    <px:PXFormView ID="form" runat="server" DataSourceID="ds" DataMember="Forwarder" Width="100%">
        <Template>
            <px:PXLayoutRule ID="PXLayoutRule1" runat="server" StartColumn="True" LabelsWidth="SM" ControlSize="M" />
            <px:PXSelector ID="edForwarderCD" runat="server" DataField="ForwarderCD" />
            <px:PXTextEdit ID="edName" runat="server" DataField="Name" />
            <px:PXCheckBox ID="chkActive" runat="server" DataField="Active" />
            <px:PXLayoutRule ID="PXLayoutRule2" runat="server" StartColumn="True" LabelsWidth="SM" ControlSize="M" />
            <px:PXTextEdit ID="edContactName" runat="server" DataField="ContactName" />
            <px:PXTextEdit ID="edPhone" runat="server" DataField="Phone" />
            <px:PXMaskEdit ID="edEmail" runat="server" DataField="Email" />
            <px:PXTextEdit ID="edWebsite" runat="server" DataField="Website" />
            <px:PXLayoutRule ID="PXLayoutRule3" runat="server" StartGroup="True" GroupCaption="API Configuration" />
            <px:PXDropDown ID="edCarrierAPIType" runat="server" DataField="CarrierAPIType" />
            <px:PXTextEdit ID="edCarrierAPIKey" runat="server" DataField="CarrierAPIKey" />
        </Template>
    </px:PXFormView>
</asp:Content>
