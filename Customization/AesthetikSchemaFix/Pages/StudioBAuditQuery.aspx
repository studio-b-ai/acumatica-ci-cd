<%@ Page Language="C#" AutoEventWireup="true" %>
<%@ Import Namespace="System.Configuration" %>
<%@ Import Namespace="System.Data.SqlClient" %>
<%@ Import Namespace="System.Web.Script.Serialization" %>
<%@ Import Namespace="System.Collections.Generic" %>
<script runat="server">
    protected void Page_Load(object sender, EventArgs e)
    {
        Response.ContentType = "application/json";
        Response.Cache.SetCacheability(HttpCacheability.NoCache);

        // Require authenticated Acumatica session
        if (!PX.Data.PXAccess.IsLoggedIn())
        {
            Response.StatusCode = 401;
            Response.Write("{\"error\":\"Not authenticated\"}");
            return;
        }

        try
        {
            string screenId = Request.QueryString["screenId"] ?? "";
            string startDate = Request.QueryString["startDate"] ?? "";
            string endDate = Request.QueryString["endDate"] ?? "";
            int top = 1000;
            int.TryParse(Request.QueryString["top"] ?? "1000", out top);
            if (top > 10000) top = 10000;
            if (top < 1) top = 100;

            var cs = ConfigurationManager.ConnectionStrings["ProjectX"];
            if (cs == null)
            {
                Response.StatusCode = 500;
                Response.Write("{\"error\":\"No database connection\"}");
                return;
            }

            var rows = new List<Dictionary<string, object>>();

            using (var conn = new SqlConnection(cs.ConnectionString))
            {
                conn.Open();

                // Build parameterized query against the VIEW
                string sql = "SELECT TOP (@top) BatchID, ChangeID, ScreenID, UserID, ChangeDate, Operation, TableName, CombinedKey, ModifiedFields FROM UsrAuditTrailView WHERE 1=1";
                var parameters = new List<SqlParameter>();
                parameters.Add(new SqlParameter("@top", top));

                if (!string.IsNullOrEmpty(screenId))
                {
                    // Support comma-separated screen IDs
                    var screens = screenId.Split(',');
                    var placeholders = new List<string>();
                    for (int i = 0; i < screens.Length; i++)
                    {
                        string pname = "@s" + i;
                        placeholders.Add(pname);
                        parameters.Add(new SqlParameter(pname, screens[i].Trim()));
                    }
                    sql += " AND ScreenID IN (" + string.Join(",", placeholders) + ")";
                }

                if (!string.IsNullOrEmpty(startDate))
                {
                    DateTime sd;
                    if (DateTime.TryParse(startDate, out sd))
                    {
                        sql += " AND ChangeDate >= @startDate";
                        parameters.Add(new SqlParameter("@startDate", sd));
                    }
                }

                if (!string.IsNullOrEmpty(endDate))
                {
                    DateTime ed;
                    if (DateTime.TryParse(endDate, out ed))
                    {
                        sql += " AND ChangeDate <= @endDate";
                        parameters.Add(new SqlParameter("@endDate", ed.AddDays(1)));
                    }
                }

                sql += " ORDER BY ChangeDate DESC";

                using (var cmd = new SqlCommand(sql, conn))
                {
                    cmd.CommandTimeout = 30;
                    foreach (var p in parameters) cmd.Parameters.Add(p);

                    using (var reader = cmd.ExecuteReader())
                    {
                        while (reader.Read())
                        {
                            var row = new Dictionary<string, object>();
                            row["BatchID"] = reader.IsDBNull(0) ? null : (object)reader.GetInt64(0);
                            row["ChangeID"] = reader.IsDBNull(1) ? null : (object)reader.GetInt64(1);
                            row["ScreenID"] = reader.IsDBNull(2) ? null : (object)reader.GetString(2).Trim();
                            row["UserID"] = reader.IsDBNull(3) ? null : (object)reader.GetGuid(3).ToString();
                            row["ChangeDate"] = reader.IsDBNull(4) ? null : (object)reader.GetDateTime(4).ToString("o");
                            row["Operation"] = reader.IsDBNull(5) ? null : (object)reader.GetString(5).Trim();
                            row["TableName"] = reader.IsDBNull(6) ? null : (object)reader.GetString(6);
                            row["CombinedKey"] = reader.IsDBNull(7) ? null : (object)reader.GetString(7);
                            row["ModifiedFields"] = reader.IsDBNull(8) ? null : (object)reader.GetString(8);
                            rows.Add(row);
                        }
                    }
                }
            }

            // Resolve UserID GUIDs to usernames via Users table
            if (rows.Count > 0)
            {
                var userIds = new HashSet<string>();
                foreach (var row in rows)
                {
                    if (row["UserID"] != null) userIds.Add(row["UserID"].ToString());
                }

                if (userIds.Count > 0)
                {
                    var userMap = new Dictionary<string, string>();
                    using (var conn2 = new SqlConnection(ConfigurationManager.ConnectionStrings["ProjectX"].ConnectionString))
                    {
                        conn2.Open();
                        var placeholders2 = new List<string>();
                        var cmd2 = new SqlCommand("", conn2);
                        int idx = 0;
                        foreach (var uid in userIds)
                        {
                            string pn = "@u" + idx;
                            placeholders2.Add(pn);
                            cmd2.Parameters.AddWithValue(pn, new Guid(uid));
                            idx++;
                        }
                        cmd2.CommandText = "SELECT CONVERT(NVARCHAR(36), PKID), Username FROM Users WHERE PKID IN (" + string.Join(",", placeholders2) + ")";
                        using (var reader2 = cmd2.ExecuteReader())
                        {
                            while (reader2.Read())
                            {
                                userMap[reader2.GetString(0).ToLower()] = reader2.GetString(1);
                            }
                        }
                    }

                    foreach (var row in rows)
                    {
                        if (row["UserID"] != null)
                        {
                            string uid = row["UserID"].ToString().ToLower();
                            if (userMap.ContainsKey(uid))
                                row["UserName"] = userMap[uid];
                        }
                    }
                }
            }

            var result = new Dictionary<string, object>();
            result["total"] = rows.Count;
            result["rows"] = rows;
            result["source"] = "UsrAuditTrailView-SQL";

            var serializer = new JavaScriptSerializer();
            serializer.MaxJsonLength = 50 * 1024 * 1024; // 50MB
            Response.Write(serializer.Serialize(result));
        }
        catch (Exception ex)
        {
            Response.StatusCode = 500;
            Response.Write("{\"error\":\"" + ex.Message.Replace("\"", "\\\"").Replace("\n", " ").Substring(0, Math.Min(ex.Message.Length, 500)) + "\"}");
        }
    }
</script>
