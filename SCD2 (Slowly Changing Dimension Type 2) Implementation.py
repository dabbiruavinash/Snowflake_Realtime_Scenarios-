CREATE OR REPLACE PROCEDURE SCD2_MERGE_PROCEDURE(
    target_table_name STRING,
    source_table_name STRING,
    business_key STRING,
    change_columns STRING
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    sql_stmt STRING;
    result STRING;
BEGIN
    -- Dynamic SQL for SCD2 merge with versioning
    sql_stmt := '
    MERGE INTO ' || target_table_name || ' AS target
    USING (
        SELECT 
            *,
            ROW_NUMBER() OVER (PARTITION BY ' || business_key || ' ORDER BY updated_at DESC) as rn
        FROM ' || source_table_name || '
    ) AS source
    ON target.' || business_key || ' = source.' || business_key || ' 
    AND target.is_current = TRUE
    WHEN MATCHED AND target.' || change_columns || ' != source.' || change_columns || ' THEN
        UPDATE SET 
            target.is_current = FALSE,
            target.end_date = CURRENT_DATE(),
            target.updated_at = CURRENT_TIMESTAMP()
    WHEN MATCHED THEN
        -- No changes, do nothing
        UPDATE SET target.updated_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN
        INSERT (' || business_key || ', col1, col2, start_date, end_date, is_current, created_at, updated_at)
        VALUES (source.' || business_key || ', source.col1, source.col2, 
                CURRENT_DATE(), NULL, TRUE, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())';
    
    -- Insert new version for changed records
    sql_stmt := sql_stmt || ';
    
    INSERT INTO ' || target_table_name || '
    SELECT 
        source.' || business_key || ',
        source.col1,
        source.col2,
        CURRENT_DATE() as start_date,
        NULL as end_date,
        TRUE as is_current,
        CURRENT_TIMESTAMP() as created_at,
        CURRENT_TIMESTAMP() as updated_at
    FROM ' || source_table_name || ' source
    WHERE EXISTS (
        SELECT 1 FROM ' || target_table_name || ' t
        WHERE t.' || business_key || ' = source.' || business_key || '
        AND t.is_current = FALSE
        AND t.' || change_columns || ' != source.' || change_columns || '
    )';
    
    EXECUTE IMMEDIATE sql_stmt;
    
    result := 'SCD2 merge completed successfully for table: ' || target_table_name;
    RETURN result;
END;
$$;