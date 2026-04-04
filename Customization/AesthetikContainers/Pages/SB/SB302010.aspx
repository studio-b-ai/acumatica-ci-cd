<%@ Page Language="C#" MasterPageFile="~/MasterPages/FormView.master" AutoEventWireup="true" ValidateRequest="false" CodeFile="SB302010.aspx.cs" Inherits="Page_SB_SB302010" Title="Container Types" %>
<%@ MasterType VirtualPath="~/MasterPages/FormView.master" %>
<asp:Content ID="cont1" ContentPlaceHolderID="phDS" Runat="Server">
    <px:PXDataSource ID="ds" runat="server" Visible="True" Width="100%"
        TypeName="StudioB.Containers.ContainerTypeMaint" PrimaryView="ContainerType">
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
    <px:PXFormView ID="form" runat="server" DataSourceID="ds" DataMember="ContainerType" Width="100%">
        <Template>
            <px:PXLayoutRule ID="PXLayoutRule1" runat="server" StartColumn="True" LabelsWidth="SM" ControlSize="M" />
            <px:PXSelector ID="edTypeCD" runat="server" DataField="TypeCD" />
            <px:PXTextEdit ID="edDescription" runat="server" DataField="Description" />
            <px:PXCheckBox ID="chkActive" runat="server" DataField="Active" />
            <px:PXLayoutRule ID="PXLayoutRule2" runat="server" StartColumn="True" LabelsWidth="SM" ControlSize="S" />
            <px:PXNumberEdit ID="edLengthFt" runat="server" DataField="LengthFt" />
            <px:PXNumberEdit ID="edWidthFt" runat="server" DataField="WidthFt" />
            <px:PXNumberEdit ID="edHeightFt" runat="server" DataField="HeightFt" />
            <px:PXNumberEdit ID="edMaxWeightKg" runat="server" DataField="MaxWeightKg" />
        </Template>
    </px:PXFormView>
</asp:Content>
