CREATE OR REPLACE PROCEDURE INCREMENTAL_LOAD_PROCEDURE(
    staging_schema STRING,
    target_schema STRING,
    table_name STRING,
    incremental_column STRING DEFAULT 'updated_at'
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    max_value STRING;
    sql_stmt STRING;
    result STRING;
BEGIN
    -- Get max value from target table
    sql_stmt := 'SELECT COALESCE(MAX(' || incremental_column || '), ''1900-01-01'') 
                 FROM ' || target_schema || '.' || table_name;
    EXECUTE IMMEDIATE sql_stmt INTO max_value;
    
    -- Perform incremental load
    sql_stmt := '
    MERGE INTO ' || target_schema || '.' || table_name || ' AS target
    USING (
        SELECT * FROM ' || staging_schema || '.' || table_name || '
        WHERE ' || incremental_column || ' > ''' || max_value || '''
    ) AS source
    ON target.id = source.id  -- Assuming id as primary key, modify as needed
    WHEN MATCHED THEN
        UPDATE SET 
            target.col1 = source.col1,
            target.col2 = source.col2,
            target.' || incremental_column || ' = source.' || incremental_column || '
    WHEN NOT MATCHED THEN
        INSERT (id, col1, col2, ' || incremental_column || ')
        VALUES (source.id, source.col1, source.col2, source.' || incremental_column || ')';
    
    EXECUTE IMMEDIATE sql_stmt;
    
    result := 'Incremental load completed for ' || table_name || 
              '. Max ' || incremental_column || ' was: ' || max_value || 
              '. Rows affected: ' || SQLROWCOUNT;
    
    RETURN result;
END;
$$;