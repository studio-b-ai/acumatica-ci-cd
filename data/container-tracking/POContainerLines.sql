-- REVIEWED: gi-sql-safe
-- GI Builder: POContainerLines

IF EXISTS (SELECT 1 FROM GIDesign WHERE Name = N'POContainerLines' AND CompanyID = 2)
BEGIN
    PRINT 'GI [POContainerLines] already exists for CompanyID 2 — skipping.';
    RETURN;
END

BEGIN TRANSACTION;
BEGIN TRY

    -- GIDesign: POContainerLines
    INSERT INTO GIDesign (DesignID, Name, ScreenID, CompanyID, CreatedByID, CreatedByScreenID, NoteID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', N'POContainerLines', N'SB401040', 2, N'B5344897-037E-4D58-B5C3-1BDFD0F47BF4', N'SM208000', N'90856bd1-37f4-40df-a080-17b1ef709485');

    -- GITable rows
    INSERT INTO GITable (DesignID, Alias, Name, CompanyID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', N'Link', N'StudioB.Containers.UsrContainerPOLink', 2);
    INSERT INTO GITable (DesignID, Alias, Name, CompanyID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', N'Container', N'StudioB.Containers.UsrContainer', 2);
    INSERT INTO GITable (DesignID, Alias, Name, CompanyID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', N'PO', N'PX.Objects.PO.POOrder', 2);
    INSERT INTO GITable (DesignID, Alias, Name, CompanyID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', N'Line', N'PX.Objects.PO.POLine', 2);

    -- GIResult rows
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 1, N'ContainerCD', 2, N'460d55b3-84fd-4a4c-99ae-9def52a76ed1');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 2, N'Status', 2, N'9f280e27-602e-4334-8d5d-becdbd49dc11');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 3, N'ETA', 2, N'86be3d6c-f2c5-440f-aedc-bcafe8e8f7df');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 4, N'OrderType', 2, N'88c5df94-5566-4d3e-92bb-7ce98e40680c');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 5, N'OrderNbr', 2, N'77d10df0-2419-4de4-a725-b24d08e5cb69');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 6, N'LineNbr', 2, N'bac60e14-67f1-42d1-abd6-7a53f2e9cedd');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 7, N'InventoryID', 2, N'6062475c-42d7-4d7c-a692-c77f5ec09073');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 8, N'OrderQty', 2, N'1c4c42f5-bd0d-48ec-bff3-825894eaa6e0');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 9, N'CuryUnitCost', 2, N'dd45cbb1-3c0d-4edc-a5b3-7ebf6c607cc2');

    -- GIFilter rows
    INSERT INTO GIFilter (DesignID, LineNbr, Name, CompanyID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 1, N'ContainerFilter', 2);
    INSERT INTO GIFilter (DesignID, LineNbr, Name, CompanyID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 2, N'POFilter', 2);

    -- GIWhere rows
    INSERT INTO GIWhere (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 1, N'Container.ContainerCD', 2);
    INSERT INTO GIWhere (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 2, N'Link.OrderNbr', 2);

    -- GISort rows
    INSERT INTO GISort (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 1, N'Container.ContainerCD', 2);
    INSERT INTO GISort (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'0566f78e-6768-4ec7-af8b-2183020c561b', 2, N'Link.OrderNbr', 2);

    -- Post-flight row count verification
    IF (SELECT COUNT(*) FROM GIDesign WHERE DesignID = N'0566f78e-6768-4ec7-af8b-2183020c561b' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GIDesign expected 1 row(s) for DesignID 0566f78e-6768-4ec7-af8b-2183020c561b', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GITable WHERE DesignID = N'0566f78e-6768-4ec7-af8b-2183020c561b' AND CompanyID = 2) <> 4
    BEGIN
        RAISERROR('Post-flight check failed: GITable expected 4 row(s) for DesignID 0566f78e-6768-4ec7-af8b-2183020c561b', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIResult WHERE DesignID = N'0566f78e-6768-4ec7-af8b-2183020c561b' AND CompanyID = 2) <> 9
    BEGIN
        RAISERROR('Post-flight check failed: GIResult expected 9 row(s) for DesignID 0566f78e-6768-4ec7-af8b-2183020c561b', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIFilter WHERE DesignID = N'0566f78e-6768-4ec7-af8b-2183020c561b' AND CompanyID = 2) <> 2
    BEGIN
        RAISERROR('Post-flight check failed: GIFilter expected 2 row(s) for DesignID 0566f78e-6768-4ec7-af8b-2183020c561b', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIWhere WHERE DesignID = N'0566f78e-6768-4ec7-af8b-2183020c561b' AND CompanyID = 2) <> 2
    BEGIN
        RAISERROR('Post-flight check failed: GIWhere expected 2 row(s) for DesignID 0566f78e-6768-4ec7-af8b-2183020c561b', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GISort WHERE DesignID = N'0566f78e-6768-4ec7-af8b-2183020c561b' AND CompanyID = 2) <> 2
    BEGIN
        RAISERROR('Post-flight check failed: GISort expected 2 row(s) for DesignID 0566f78e-6768-4ec7-af8b-2183020c561b', 16, 1);
    END

    COMMIT TRANSACTION;
    PRINT 'GI [POContainerLines] created successfully.';

END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    DECLARE @ErrMsg NVARCHAR(4000) = ERROR_MESSAGE();
    DECLARE @ErrSev INT = ERROR_SEVERITY();
    DECLARE @ErrState INT = ERROR_STATE();
    PRINT 'GI [POContainerLines] creation FAILED: ' + @ErrMsg;
    RAISERROR(@ErrMsg, @ErrSev, @ErrState);
END CATCH