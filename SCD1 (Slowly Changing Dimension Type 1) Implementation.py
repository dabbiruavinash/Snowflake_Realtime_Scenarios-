CREATE OR REPLACE PROCEDURE SCD1_MERGE_PROCEDURE(
    target_table_name STRING,
    source_table_name STRING,
    business_key STRING
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    sql_stmt STRING;
    result STRING;
BEGIN
    -- Dynamic SQL for SCD1 merge
    sql_stmt := '
    MERGE INTO ' || target_table_name || ' AS target
    USING ' || source_table_name || ' AS source
    ON target.' || business_key || ' = source.' || business_key || '
    WHEN MATCHED THEN 
        UPDATE SET 
            target.col1 = source.col1,
            target.col2 = source.col2,
            target.updated_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN
        INSERT (' || business_key || ', col1, col2, created_at, updated_at)
        VALUES (source.' || business_key || ', source.col1, source.col2, 
                CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP())';
    
    EXECUTE IMMEDIATE sql_stmt;
    
    result := 'SCD1 merge completed successfully for table: ' || target_table_name;
    RETURN result;
END;
$$;