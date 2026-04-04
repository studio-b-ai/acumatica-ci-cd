-- REVIEWED: gi-sql-safe
-- GI Builder: CustomClassification

IF EXISTS (SELECT 1 FROM GIDesign WHERE Name = N'CustomClassification' AND CompanyID = 2)
BEGIN
    PRINT 'GI [CustomClassification] already exists for CompanyID 2 — skipping.';
    RETURN;
END

BEGIN TRANSACTION;
BEGIN TRY

    -- GIDesign: CustomClassification
    INSERT INTO GIDesign (DesignID, Name, ScreenID, CompanyID, CreatedByID, CreatedByScreenID, NoteID) VALUES (N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa', N'CustomClassification', N'SB401030', 2, N'B5344897-037E-4D58-B5C3-1BDFD0F47BF4', N'SM208000', N'fa0fcf3d-880c-4210-a455-75318e547863');

    -- GITable rows
    INSERT INTO GITable (DesignID, Alias, Name, CompanyID) VALUES (N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa', N'Item', N'PX.Objects.IN.InventoryItem', 2);

    -- GIResult rows
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 1, N'InventoryCD', 2, N'4ae7f836-7648-4f1a-bf16-b9d1db852817');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 2, N'Descr', 2, N'b44a65ae-d870-4706-b69a-5c8d96ca40b7');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 3, N'ItemClassID', 2, N'bcf2c4b7-b19c-45bb-82d3-7db0ac761844');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 4, N'UsrFiberContent', 2, N'a5e693c1-55ff-4424-a821-c54850e588cd');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 5, N'UsrDutyRate', 2, N'32b92b71-0d3b-41d9-a6f1-a2e2be1ff8f6');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 6, N'UsrPreferentialTariff', 2, N'bc0d7ab3-2e7d-44be-a6c6-0114a6db4fea');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 7, N'UsrFreightClass', 2, N'e15b7a90-3ab0-4667-b6a6-09b4f8d0d12b');

    -- GIFilter rows
    INSERT INTO GIFilter (DesignID, LineNbr, Name, CompanyID) VALUES (N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 1, N'ItemClassFilter', 2);

    -- GIWhere rows
    INSERT INTO GIWhere (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 1, N'Item.ItemClassID', 2);

    -- GISort rows
    INSERT INTO GISort (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 1, N'Item.InventoryCD', 2);

    -- Post-flight row count verification
    IF (SELECT COUNT(*) FROM GIDesign WHERE DesignID = N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GIDesign expected 1 row(s) for DesignID 79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GITable WHERE DesignID = N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GITable expected 1 row(s) for DesignID 79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIResult WHERE DesignID = N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa' AND CompanyID = 2) <> 7
    BEGIN
        RAISERROR('Post-flight check failed: GIResult expected 7 row(s) for DesignID 79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIFilter WHERE DesignID = N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GIFilter expected 1 row(s) for DesignID 79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIWhere WHERE DesignID = N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GIWhere expected 1 row(s) for DesignID 79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GISort WHERE DesignID = N'79538136-ed3f-47f8-9ab1-7efdb53fc1aa' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GISort expected 1 row(s) for DesignID 79538136-ed3f-47f8-9ab1-7efdb53fc1aa', 16, 1);
    END

    COMMIT TRANSACTION;
    PRINT 'GI [CustomClassification] created successfully.';

END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    DECLARE @ErrMsg NVARCHAR(4000) = ERROR_MESSAGE();
    DECLARE @ErrSev INT = ERROR_SEVERITY();
    DECLARE @ErrState INT = ERROR_STATE();
    PRINT 'GI [CustomClassification] creation FAILED: ' + @ErrMsg;
    RAISERROR(@ErrMsg, @ErrSev, @ErrState);
END CATCH