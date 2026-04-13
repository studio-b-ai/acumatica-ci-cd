#!/usr/bin/env python3
"""Build a minimal customization package with DROP TABLE KNMCSalesPriceSyncData."""

import os
import zipfile

OUT = "drop-table-package.zip"

PROJECT_XML = """<?xml version="1.0" encoding="utf-8"?>
<Customization level="0" description="One-off: Drop KNMCSalesPriceSyncData table" product-version="24.208">

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

</Customization>
"""

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("project.xml", PROJECT_XML)

print(f"Built {OUT} ({os.path.getsize(OUT)} bytes)")
