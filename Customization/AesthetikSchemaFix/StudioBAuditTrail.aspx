<%@ Page Language="C#" AutoEventWireup="true" %>
<script runat="server">
    protected void Page_Init(object sender, EventArgs e)
    {
        StudioB.Api.AuditTrailHandler.ProcessRequest(HttpContext.Current);
        Response.End();
    }
</script>
