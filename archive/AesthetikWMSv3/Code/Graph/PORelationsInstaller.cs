using Customization;
using PX.Data;

namespace StudioB.PO
{
    public class PORelationsInstaller : CustomizationPlugin
    {
        public override void UpdateDatabase()
        {
            // Get connection string from web.config
            string connStr = null;
            try
            {
                var cs = System.Configuration.ConfigurationManager.ConnectionStrings["ProjectX"];
                if (cs != null) connStr = cs.ConnectionString;
            }
            catch { }

            if (connStr == null)
            {
                // Fallback: scan all connection strings
                try
                {
                    var allCs = System.Configuration.ConfigurationManager.ConnectionStrings;
                    for (int i = 0; i < allCs.Count; i++)
                    {
                        if (allCs[i].Name != "LocalSqlServer" && allCs[i].Name != "LocalMySqlServer")
                            connStr = allCs[i].ConnectionString;
                    }
                }
                catch { }
            }

            if (connStr == null)
            {
                WriteLog("StudioB PO Relations: No connection string found — cannot create tables");
                return;
            }

            // Microsoft.Data.SqlClient requires explicit SSL trust for cloud SQL
            if (!connStr.Contains("TrustServerCertificate"))
                connStr += ";TrustServerCertificate=True";

            // Create UsrPORelation
            ExecuteDDL(connStr, "UsrPORelation", @"
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'UsrPORelation')
CREATE TABLE UsrPORelation (
    CompanyID INT NOT NULL DEFAULT 0,
    UsrPORelationID INT IDENTITY(1,1) NOT NULL,
    RefNoteID UNIQUEIDENTIFIER NULL,
    Role NVARCHAR(50) NULL,
    ContactName NVARCHAR(100) NULL,
    Email NVARCHAR(100) NULL,
    Phone NVARCHAR(50) NULL,
    Company NVARCHAR(100) NULL,
    AddToCC BIT NULL DEFAULT 0,
    IsActive BIT NULL DEFAULT 1,
    CreatedByID UNIQUEIDENTIFIER NULL,
    CreatedByScreenID CHAR(8) NULL,
    CreatedDateTime DATETIME NULL,
    LastModifiedByID UNIQUEIDENTIFIER NULL,
    LastModifiedByScreenID CHAR(8) NULL,
    LastModifiedDateTime DATETIME NULL,
    tstamp TIMESTAMP NOT NULL,
    CONSTRAINT PK_UsrPORelation PRIMARY KEY CLUSTERED (CompanyID, UsrPORelationID)
)");

            // Create UsrPOActivity
            ExecuteDDL(connStr, "UsrPOActivity", @"
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'UsrPOActivity')
CREATE TABLE UsrPOActivity (
    CompanyID INT NOT NULL DEFAULT 0,
    UsrPOActivityID INT IDENTITY(1,1) NOT NULL,
    RefNoteID UNIQUEIDENTIFIER NULL,
    Type CHAR(2) NULL DEFAULT 'NT',
    Subject NVARCHAR(255) NULL,
    Body NVARCHAR(MAX) NULL,
    Status CHAR(2) NULL DEFAULT 'OP',
    Priority CHAR(1) NULL DEFAULT 'N',
    StartDate DATETIME NULL,
    OwnerID NVARCHAR(100) NULL,
    CreatedByID UNIQUEIDENTIFIER NULL,
    CreatedByScreenID CHAR(8) NULL,
    CreatedDateTime DATETIME NULL,
    LastModifiedByID UNIQUEIDENTIFIER NULL,
    LastModifiedByScreenID CHAR(8) NULL,
    LastModifiedDateTime DATETIME NULL,
    tstamp TIMESTAMP NOT NULL,
    CONSTRAINT PK_UsrPOActivity PRIMARY KEY CLUSTERED (CompanyID, UsrPOActivityID)
)");

            // Create indexes
            ExecuteDDL(connStr, "IX_UsrPORelation_RefNoteID",
                "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_UsrPORelation_RefNoteID') CREATE INDEX IX_UsrPORelation_RefNoteID ON UsrPORelation(CompanyID, RefNoteID)");

            ExecuteDDL(connStr, "IX_UsrPOActivity_RefNoteID",
                "IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_UsrPOActivity_RefNoteID') CREATE INDEX IX_UsrPOActivity_RefNoteID ON UsrPOActivity(CompanyID, RefNoteID)");

            WriteLog("StudioB PO Relations: UpdateDatabase complete");
        }

        private void ExecuteDDL(string connStr, string label, string sql)
        {
            try
            {
                using (var conn = new Microsoft.Data.SqlClient.SqlConnection(connStr))
                {
                    conn.Open();
                    using (var cmd = conn.CreateCommand())
                    {
                        cmd.CommandText = sql;
                        cmd.CommandTimeout = 60;
                        cmd.ExecuteNonQuery();
                    }
                }
                WriteLog("StudioB PO Relations: " + label + " — OK");
            }
            catch (System.Exception ex)
            {
                WriteLog("StudioB PO Relations: " + label + " — FAILED: " + ex.GetType().FullName + ": " + ex.Message);
            }
        }
    }
}
