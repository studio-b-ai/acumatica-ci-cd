<%@ Page Language="C#" MasterPageFile="~/MasterPages/TabView.master"
    AutoEventWireup="true" ValidateRequest="false"
    CodeFile="SB501200.aspx.cs" Inherits="Page_SB_SB501200"
    Title="Supplier Intake" %>
<%@ MasterType VirtualPath="~/MasterPages/TabView.master" %>
<asp:Content ID="cont1" ContentPlaceHolderID="phDS" Runat="Server">
    <px:PXDataSource ID="ds" runat="server" Visible="True" Width="100%"
        TypeName="StudioB.Containers.SupplierIntake" PrimaryView="Filter">
    </px:PXDataSource>
</asp:Content>
<asp:Content ID="cont2" ContentPlaceHolderID="phF" Runat="Server">
    <px:PXFormView ID="form" runat="server" DataSourceID="ds"
        DataMember="Filter" Width="100%">
        <Template>
            <px:PXHtmlView ID="htmlIntake" runat="server"
                DataField="IntakeUrl" Height="800px" Width="100%"
                SkinID="Label" />
        </Template>
    </px:PXFormView>
</asp:Content>
