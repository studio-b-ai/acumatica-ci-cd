-- REVIEWED: gi-sql-safe
-- GI Builder: UserAuditTrail

IF EXISTS (SELECT 1 FROM GIDesign WHERE Name = N'UserAuditTrail' AND CompanyID = 2)
BEGIN
    PRINT 'GI [UserAuditTrail] already exists for CompanyID 2 — skipping.';
    RETURN;
END

BEGIN TRANSACTION;
BEGIN TRY

    -- GIDesign: UserAuditTrail
    INSERT INTO GIDesign (DesignID, Name, ScreenID, CompanyID, CreatedByID, CreatedByScreenID, NoteID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', N'UserAuditTrail', N'GI000099', 2, N'B5344897-037E-4D58-B5C3-1BDFD0F47BF4', N'SM208000', N'f904e99a-7aff-40f7-8816-ad8f2e17aadf');

    -- GITable rows
    INSERT INTO GITable (DesignID, Alias, Name, CompanyID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', N'AuditHistory', N'PX.SM.AuditHistory', 2);

    -- GIResult rows
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 1, N'ScreenID', 2, N'dfeaf6b9-c0f8-4764-9b42-ba4a080633a4');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 2, N'Operation', 2, N'8f44b392-a073-4d64-88c0-289c5efa8df9');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 3, N'ChangeDate', 2, N'6221a1e1-231d-49e5-964b-36c3812193a7');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 4, N'TableName', 2, N'3b8c8eed-cdaa-4cee-8bb5-8a9d6953d668');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 5, N'BatchID', 2, N'f8d3438c-37da-4ac7-972b-f609d5e23dec');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 6, N'ChangeID', 2, N'95100738-6ad1-43b8-9fd8-a7351076228a');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 7, N'CombinedKey', 2, N'7a946d43-61df-490f-9ea6-93cb4203b64c');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 8, N'ModifiedFields', 2, N'928c691c-4a69-4bf3-8b2e-b943ae4cc1b5');
    INSERT INTO GIResult (DesignID, LineNbr, Field, CompanyID, RowID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 9, N'UserID', 2, N'50109609-1f83-4cff-99b1-2f9d51297a5c');

    -- GIFilter rows
    INSERT INTO GIFilter (DesignID, LineNbr, Name, CompanyID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 1, N'ScreenFilter', 2);
    INSERT INTO GIFilter (DesignID, LineNbr, Name, CompanyID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 2, N'FromDate', 2);
    INSERT INTO GIFilter (DesignID, LineNbr, Name, CompanyID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 3, N'ToDate', 2);

    -- GIWhere rows
    INSERT INTO GIWhere (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 1, N'AuditHistory.ScreenID', 2);
    INSERT INTO GIWhere (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 2, N'AuditHistory.ChangeDate', 2);
    INSERT INTO GIWhere (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 3, N'AuditHistory.ChangeDate', 2);

    -- GISort rows
    INSERT INTO GISort (DesignID, LineNbr, DataFieldName, CompanyID) VALUES (N'7f70fe9e-c4e8-46c6-86d7-821e87f28029', 1, N'AuditHistory.ChangeDate', 2);

    -- Post-flight row count verification
    IF (SELECT COUNT(*) FROM GIDesign WHERE DesignID = N'7f70fe9e-c4e8-46c6-86d7-821e87f28029' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GIDesign expected 1 row(s) for DesignID 7f70fe9e-c4e8-46c6-86d7-821e87f28029', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GITable WHERE DesignID = N'7f70fe9e-c4e8-46c6-86d7-821e87f28029' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GITable expected 1 row(s) for DesignID 7f70fe9e-c4e8-46c6-86d7-821e87f28029', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIResult WHERE DesignID = N'7f70fe9e-c4e8-46c6-86d7-821e87f28029' AND CompanyID = 2) <> 9
    BEGIN
        RAISERROR('Post-flight check failed: GIResult expected 9 row(s) for DesignID 7f70fe9e-c4e8-46c6-86d7-821e87f28029', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIFilter WHERE DesignID = N'7f70fe9e-c4e8-46c6-86d7-821e87f28029' AND CompanyID = 2) <> 3
    BEGIN
        RAISERROR('Post-flight check failed: GIFilter expected 3 row(s) for DesignID 7f70fe9e-c4e8-46c6-86d7-821e87f28029', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GIWhere WHERE DesignID = N'7f70fe9e-c4e8-46c6-86d7-821e87f28029' AND CompanyID = 2) <> 3
    BEGIN
        RAISERROR('Post-flight check failed: GIWhere expected 3 row(s) for DesignID 7f70fe9e-c4e8-46c6-86d7-821e87f28029', 16, 1);
    END
    IF (SELECT COUNT(*) FROM GISort WHERE DesignID = N'7f70fe9e-c4e8-46c6-86d7-821e87f28029' AND CompanyID = 2) <> 1
    BEGIN
        RAISERROR('Post-flight check failed: GISort expected 1 row(s) for DesignID 7f70fe9e-c4e8-46c6-86d7-821e87f28029', 16, 1);
    END

    COMMIT TRANSACTION;
    PRINT 'GI [UserAuditTrail] created successfully.';

END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    DECLARE @ErrMsg NVARCHAR(4000) = ERROR_MESSAGE();
    DECLARE @ErrSev INT = ERROR_SEVERITY();
    DECLARE @ErrState INT = ERROR_STATE();
    PRINT 'GI [UserAuditTrail] creation FAILED: ' + @ErrMsg;
    RAISERROR(@ErrMsg, @ErrSev, @ErrState);
END CATCH