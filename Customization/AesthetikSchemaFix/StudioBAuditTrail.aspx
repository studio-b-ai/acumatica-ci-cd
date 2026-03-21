<%@ Page Language="C#" AutoEventWireup="true" %>
<%@ Assembly Name="App_RuntimeCode" %>
<%@ Import Namespace="StudioB.Api" %>
<script runat="server">
    protected void Page_Init(object sender, EventArgs e)
    {
        AuditTrailHandler.ProcessRequest(HttpContext.Current);
        Response.End();
    }
</script>
