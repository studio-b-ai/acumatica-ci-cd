-- REVIEWED: gi-sql-safe
-- GI Builder: SOContainers

IF EXISTS (SELECT 1 FROM GIDesign WHERE Name = N'SOContainers' AND CompanyID = 2)
BEGIN
    PRINT 'GI [SOContainers] already exists for CompanyID 2 — skipping.';
    RETURN;
END

BEGIN TRANSACTION;
BEGIN TRY

    -- GIDesign: SOContainers
    INSERT INTO GIDesign (DesignID, Name, ScreenID, CompanyID, CreatedByID, CreatedByScreenID, NoteID) VALUES (N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef', N'SOContainers', N'SB401010', 2, N'B5344897-037E-4D58-B5C3-1BDFD0F47BF4', N'SM208000', N'e4bfce1a-9d92-423d-bd9d-c6bc1059c182');

    -- GITable rows
    INSERT INTO GITable (DesignID, Alias, Name, CompanyID) VALUES (N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef', N'Shipment', N'PX.Objects.SO.SOShipment', 2);

    -- GIResult rows
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 1, N'ShipmentNbr', 2, N'2729b009-cfca-472e-8400-0ef5cfd3992d');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 2, N'Status', 2, N'6204fa19-6814-411a-9b3a-9b9128a1434a');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 3, N'CustomerID', 2, N'ae0b25d7-ab2a-4999-8579-7d19701f8f04');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 4, N'ShipDate', 2, N'82d32081-98aa-49bb-bfc2-b6329dc5ae7b');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 5, N'UsrContainerID', 2, N'36b548f1-e768-4a1a-8efd-15ebba36df22');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 6, N'UsrIncludeInContainer', 2, N'714189fb-24e7-46c7-97cb-a69ff730b624');

    -- GIFilter rows
    INSERT INTO GIFilter (DesignID, LineNbr, Name, CompanyID) VALUES (N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 1, N'StatusFilter', 2);

    -- GIWhere rows
    INSERT INTO GIWhere (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 1, N'Shipment.Status', 2);

    -- GISort rows
    INSERT INTO GISort (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 1, N'Shipment.ShipDate', 2);

    -- Post-flight row count verification
    IF (SELECT COUNT(*) FROM GIDesign WHERE DesignID = N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GIDesign expected 1 row(s) for DesignID bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GITable WHERE DesignID = N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GITable expected 1 row(s) for DesignID bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIResult WHERE DesignID = N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef' AND CompanyID = 2) <> 6
    BEGIN
        RAISERROR('Post-flight check failed: GIResult expected 6 row(s) for DesignID bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIFilter WHERE DesignID = N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GIFilter expected 1 row(s) for DesignID bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIWhere WHERE DesignID = N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GIWhere expected 1 row(s) for DesignID bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GISort WHERE DesignID = N'bb6ccce3-12ba-4f8d-8b6b-714305d579ef' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GISort expected 1 row(s) for DesignID bb6ccce3-12ba-4f8d-8b6b-714305d579ef', 16, 1);
    END

    COMMIT TRANSACTION;
    PRINT 'GI [SOContainers] created successfully.';

END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    DECLARE @ErrMsg NVARCHAR(4000) = ERROR_MESSAGE();
    DECLARE @ErrSev INT = ERROR_SEVERITY();
    DECLARE @ErrState INT = ERROR_STATE();
    PRINT 'GI [SOContainers] creation FAILED: ' + @ErrMsg;
    RAISERROR(@ErrMsg, @ErrSev, @ErrState);
END CATCH