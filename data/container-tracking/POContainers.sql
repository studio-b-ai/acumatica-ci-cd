-- REVIEWED: gi-sql-safe
-- GI Builder: POContainers

IF EXISTS (SELECT 1 FROM GIDesign WHERE Name = N'POContainers' AND CompanyID = 2)
BEGIN
    PRINT 'GI [POContainers] already exists for CompanyID 2 — skipping.';
    RETURN;
END

BEGIN TRANSACTION;
BEGIN TRY

    -- GIDesign: POContainers
    INSERT INTO GIDesign (DesignID, Name, ScreenID, CompanyID, CreatedByID, CreatedByScreenID, NoteID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', N'POContainers', N'SB401000', 2, N'B5344897-037E-4D58-B5C3-1BDFD0F47BF4', N'SM208000', N'4b5862fb-bb1b-47bd-9f52-60d5822e7fb7');

    -- GITable rows
    INSERT INTO GITable (DesignID, Alias, Name, CompanyID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', N'Container', N'StudioB.Containers.UsrContainer', 2);

    -- GIResult rows
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 1, N'ContainerCD', 2, N'60e47900-9f24-4f83-baac-65fa346f9735');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 2, N'Status', 2, N'4c13fa66-4b87-42c7-8e3b-f7b1f2d51974');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 3, N'CarrierCode', 2, N'949c5714-f220-42df-9964-016565399810');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 4, N'VesselName', 2, N'4162fe30-afa4-471e-95c8-af50e47775a9');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 5, N'PortOfLoading', 2, N'ef306f39-ae6e-4df7-b39b-ad2ee82db31f');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 6, N'PortOfDischarge', 2, N'16ee8909-e9b0-4096-8b90-1b3af4fce6b1');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 7, N'ETD', 2, N'9d56892b-5010-49a2-b090-44eacb1b1c4e');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 8, N'ETA', 2, N'bb431ee3-7be2-4f87-bf6e-665ad469472a');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 9, N'ATA', 2, N'4b642ed3-3171-4b46-bf95-1cc0849db496');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 10, N'ContainerType', 2, N'03e993f9-34e5-4734-bff1-a42c2a12bacf');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 11, N'BookingRef', 2, N'2fcee3af-b8c5-4fe8-8259-f240cbaab9b9');

    -- GIFilter rows
    INSERT INTO GIFilter (DesignID, LineNbr, Name, CompanyID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 1, N'StatusFilter', 2);
    INSERT INTO GIFilter (DesignID, LineNbr, Name, CompanyID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 2, N'CarrierFilter', 2);

    -- GIWhere rows
    INSERT INTO GIWhere (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 1, N'Container.Status', 2);
    INSERT INTO GIWhere (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 2, N'Container.CarrierCode', 2);

    -- GISort rows
    INSERT INTO GISort (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'0a2b8dab-1987-46c5-bde1-44f4c6730897', 1, N'Container.ETA', 2);

    -- Post-flight row count verification
    IF (SELECT COUNT(*) FROM GIDesign WHERE DesignID = N'0a2b8dab-1987-46c5-bde1-44f4c6730897' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GIDesign expected 1 row(s) for DesignID 0a2b8dab-1987-46c5-bde1-44f4c6730897', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GITable WHERE DesignID = N'0a2b8dab-1987-46c5-bde1-44f4c6730897' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GITable expected 1 row(s) for DesignID 0a2b8dab-1987-46c5-bde1-44f4c6730897', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIResult WHERE DesignID = N'0a2b8dab-1987-46c5-bde1-44f4c6730897' AND CompanyID = 2) <> 11
    BEGIN
        RAISERROR('Post-flight check failed: GIResult expected 11 row(s) for DesignID 0a2b8dab-1987-46c5-bde1-44f4c6730897', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIFilter WHERE DesignID = N'0a2b8dab-1987-46c5-bde1-44f4c6730897' AND CompanyID = 2) <> 2
    BEGIN
        RAISERROR('Post-flight check failed: GIFilter expected 2 row(s) for DesignID 0a2b8dab-1987-46c5-bde1-44f4c6730897', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIWhere WHERE DesignID = N'0a2b8dab-1987-46c5-bde1-44f4c6730897' AND CompanyID = 2) <> 2
    BEGIN
        RAISERROR('Post-flight check failed: GIWhere expected 2 row(s) for DesignID 0a2b8dab-1987-46c5-bde1-44f4c6730897', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GISort WHERE DesignID = N'0a2b8dab-1987-46c5-bde1-44f4c6730897' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GISort expected 1 row(s) for DesignID 0a2b8dab-1987-46c5-bde1-44f4c6730897', 16, 1);
    END

    COMMIT TRANSACTION;
    PRINT 'GI [POContainers] created successfully.';

END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    DECLARE @ErrMsg NVARCHAR(4000) = ERROR_MESSAGE();
    DECLARE @ErrSev INT = ERROR_SEVERITY();
    DECLARE @ErrState INT = ERROR_STATE();
    PRINT 'GI [POContainers] creation FAILED: ' + @ErrMsg;
    RAISERROR(@ErrMsg, @ErrSev, @ErrState);
END CATCH