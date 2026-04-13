#!/usr/bin/env python3
"""Build a StudioBAcuOps package with DROP TABLE KNMCSalesPriceSyncData injected."""

import os
import zipfile

SRC = os.path.join(os.path.dirname(__file__), "..", "Customization", "StudioBAcuOps", "project.xml")
OUT = "drop-table-package.zip"

DROP_SQL = """
    <Sql Name="DropKNMCSalesPriceSyncData" Script="#CDATA">
        <CDATA name="Script"><![CDATA[IF OBJECT_ID('dbo.KNMCSalesPriceSyncData', 'U') IS NOT NULL
BEGIN
    DROP TABLE dbo.KNMCSalesPriceSyncData;
    PRINT 'Dropped table KNMCSalesPriceSyncData';
END
ELSE
BEGIN
    PRINT 'Table KNMCSalesPriceSyncData does not exist';
END
        ]]></CDATA>
    </Sql>
"""

with open(SRC, "r") as f:
    content = f.read()

content = content.replace("</Customization>", DROP_SQL + "\n</Customization>")

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("project.xml", content)

print(f"Built {OUT} ({os.path.getsize(OUT)} bytes)")
