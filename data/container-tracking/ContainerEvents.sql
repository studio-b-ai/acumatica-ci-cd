-- REVIEWED: gi-sql-safe
-- GI Builder: ContainerEvents

IF EXISTS (SELECT 1 FROM GIDesign WHERE Name = N'ContainerEvents' AND CompanyID = 2)
BEGIN
    PRINT 'GI [ContainerEvents] already exists for CompanyID 2 — skipping.';
    RETURN;
END

BEGIN TRANSACTION;
BEGIN TRY

    -- GIDesign: ContainerEvents
    INSERT INTO GIDesign (DesignID, Name, ScreenID, CompanyID, CreatedByID, CreatedByScreenID, NoteID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', N'ContainerEvents', N'SB401020', 2, N'B5344897-037E-4D58-B5C3-1BDFD0F47BF4', N'SM208000', N'2e35e69c-9a9c-40f8-8974-30edfd5f81f2');

    -- GITable rows
    INSERT INTO GITable (DesignID, Alias, Name, CompanyID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', N'Event', N'StudioB.Containers.UsrContainerEvent', 2);
    INSERT INTO GITable (DesignID, Alias, Name, CompanyID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', N'Container', N'StudioB.Containers.UsrContainer', 2);

    -- GIResult rows
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', 1, N'ContainerCD', 2, N'00124187-88b5-4f14-b248-06673e459a98');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', 2, N'EventDateTime', 2, N'4fb223f9-71b9-43e5-a2ba-1b45bd4d616c');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', 3, N'NormalizedEventCode', 2, N'97497633-27fe-49cd-8142-2bd5965c399f');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', 4, N'EventClassifier', 2, N'6dbcbcb6-d298-46fc-bbf4-4313f743e5f3');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', 5, N'LocationName', 2, N'0ea28e22-67ba-4d46-bc7d-bae111e14c63');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', 6, N'VesselName', 2, N'4d1ae20b-6d95-4dc9-90d8-4c33e32e126c');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', 7, N'Description', 2, N'62ed1858-64a8-42a3-9198-7150f869715f');

    -- GIFilter rows
    INSERT INTO GIFilter (DesignID, LineNbr, Name, CompanyID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', 1, N'ContainerFilter', 2);
    INSERT INTO GIFilter (DesignID, LineNbr, Name, CompanyID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', 2, N'EventCodeFilter', 2);

    -- GIWhere rows
    INSERT INTO GIWhere (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', 1, N'Container.ContainerCD', 2);
    INSERT INTO GIWhere (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', 2, N'Event.NormalizedEventCode', 2);

    -- GISort rows
    INSERT INTO GISort (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'84272c7f-4e52-484b-b4bf-0cdb40e38257', 1, N'Event.EventDateTime', 2);

    -- Post-flight row count verification
    IF (SELECT COUNT(*) FROM GIDesign WHERE DesignID = N'84272c7f-4e52-484b-b4bf-0cdb40e38257' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GIDesign expected 1 row(s) for DesignID 84272c7f-4e52-484b-b4bf-0cdb40e38257', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GITable WHERE DesignID = N'84272c7f-4e52-484b-b4bf-0cdb40e38257' AND CompanyID = 2) <> 2
    BEGIN
        RAISERROR('Post-flight check failed: GITable expected 2 row(s) for DesignID 84272c7f-4e52-484b-b4bf-0cdb40e38257', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIResult WHERE DesignID = N'84272c7f-4e52-484b-b4bf-0cdb40e38257' AND CompanyID = 2) <> 7
    BEGIN
        RAISERROR('Post-flight check failed: GIResult expected 7 row(s) for DesignID 84272c7f-4e52-484b-b4bf-0cdb40e38257', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIFilter WHERE DesignID = N'84272c7f-4e52-484b-b4bf-0cdb40e38257' AND CompanyID = 2) <> 2
    BEGIN
        RAISERROR('Post-flight check failed: GIFilter expected 2 row(s) for DesignID 84272c7f-4e52-484b-b4bf-0cdb40e38257', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIWhere WHERE DesignID = N'84272c7f-4e52-484b-b4bf-0cdb40e38257' AND CompanyID = 2) <> 2
    BEGIN
        RAISERROR('Post-flight check failed: GIWhere expected 2 row(s) for DesignID 84272c7f-4e52-484b-b4bf-0cdb40e38257', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GISort WHERE DesignID = N'84272c7f-4e52-484b-b4bf-0cdb40e38257' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GISort expected 1 row(s) for DesignID 84272c7f-4e52-484b-b4bf-0cdb40e38257', 16, 1);
    END

    COMMIT TRANSACTION;
    PRINT 'GI [ContainerEvents] created successfully.';

END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    DECLARE @ErrMsg NVARCHAR(4000) = ERROR_MESSAGE();
    DECLARE @ErrSev INT = ERROR_SEVERITY();
    DECLARE @ErrState INT = ERROR_STATE();
    PRINT 'GI [ContainerEvents] creation FAILED: ' + @ErrMsg;
    RAISERROR(@ErrMsg, @ErrSev, @ErrState);
END CATCH