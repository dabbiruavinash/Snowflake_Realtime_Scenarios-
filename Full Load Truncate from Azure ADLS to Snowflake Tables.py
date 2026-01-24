CREATE OR REPLACE PROCEDURE FULL_LOAD_ADLS_TO_SNOWFLAKE(
    storage_integration_name STRING,
    adls_container_name STRING,
    adls_folder_path STRING,
    file_format_name STRING,
    target_schema STRING,
    target_table STRING,
    stage_name STRING DEFAULT NULL
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    full_stage_name STRING;
    file_pattern STRING;
    copy_command STRING;
    result STRING;
    file_list ARRAY;
    sql_stmt STRING;
BEGIN
    -- Build stage name if not provided
    IF (stage_name IS NULL) THEN
        full_stage_name := '@' || target_schema || '.' || UPPER(target_table) || '_STAGE';
    ELSE
        full_stage_name := '@' || stage_name;
    END IF;
    
    -- Create external stage if not exists
    sql_stmt := '
    CREATE OR REPLACE STAGE ' || REPLACE(full_stage_name, '@', '') || '
    STORAGE_INTEGRATION = ' || storage_integration_name || '
    URL = ''azure://' || adls_container_name || '.blob.core.windows.net/' || adls_folder_path || '''
    FILE_FORMAT = ' || file_format_name || ';';
    
    EXECUTE IMMEDIATE sql_stmt;
    
    -- List files in stage
    sql_stmt := 'LIST ' || full_stage_name || ';';
    LET c1 CURSOR FOR sql_stmt;
    OPEN c1;
    FETCH c1 INTO file_list;
    CLOSE c1;
    
    IF (ARRAY_SIZE(file_list) = 0) THEN
        RETURN 'No files found in ADLS path: ' || adls_folder_path;
    END IF;
    
    -- Truncate target table
    sql_stmt := 'TRUNCATE TABLE ' || target_schema || '.' || target_table || ';';
    EXECUTE IMMEDIATE sql_stmt;
    
    -- Load data from ADLS
    copy_command := '
    COPY INTO ' || target_schema || '.' || target_table || '
    FROM ' || full_stage_name || '
    FILE_FORMAT = (FORMAT_NAME = ''' || file_format_name || ''')
    ON_ERROR = ''CONTINUE''
    PURGE = TRUE;';
    
    EXECUTE IMMEDIATE copy_command;
    
    -- Validate load
    sql_stmt := '
    SELECT 
        COUNT(*) as total_rows,
        COUNT(DISTINCT METADATA$FILENAME) as files_loaded
    FROM ' || target_schema || '.' || target_table || ';';
    
    LET validation_result RESULTSET := (EXECUTE IMMEDIATE sql_stmt);
    LET row_count INT;
    LET files_loaded INT;
    FETCH validation_result INTO row_count, files_loaded;
    
    result := 'Full load completed successfully.' || '\n' ||
              'Target Table: ' || target_schema || '.' || target_table || '\n' ||
              'ADLS Path: ' || adls_folder_path || '\n' ||
              'Files Loaded: ' || files_loaded || '\n' ||
              'Rows Inserted: ' || row_count;
    
    RETURN result;
EXCEPTION
    WHEN OTHER THEN
        RETURN 'Error: ' || SQLERRM || ' - SQLSTATE: ' || SQLSTATE;
END;
$$;

-- Supporting procedure for partitioned loads
CREATE OR REPLACE PROCEDURE FULL_LOAD_PARTITIONED_ADLS(
    storage_integration_name STRING,
    adls_container_name STRING,
    adls_base_path STRING,
    file_format_name STRING,
    target_schema STRING,
    target_table STRING,
    partition_column STRING,
    partition_value STRING
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    stage_name STRING;
    adls_partition_path STRING;
    sql_stmt STRING;
    result STRING;
BEGIN
    -- Construct partition path
    adls_partition_path := adls_base_path || '/' || partition_column || '=' || partition_value || '/';
    
    -- Create stage for partition
    stage_name := 'PARTITION_STAGE_' || REPLACE(partition_value, '-', '_');
    
    sql_stmt := '
    CREATE OR REPLACE STAGE ' || stage_name || '
    STORAGE_INTEGRATION = ' || storage_integration_name || '
    URL = ''azure://' || adls_container_name || '.blob.core.windows.net/' || adls_partition_path || '''
    FILE_FORMAT = ' || file_format_name || ';';
    
    EXECUTE IMMEDIATE sql_stmt;
    
    -- Delete existing partition data
    sql_stmt := '
    DELETE FROM ' || target_schema || '.' || target_table || '
    WHERE ' || partition_column || ' = ''' || partition_value || ''';';
    
    EXECUTE IMMEDIATE sql_stmt;
    
    -- Load partition data
    sql_stmt := '
    COPY INTO ' || target_schema || '.' || target_table || '
    FROM @' || stage_name || '
    FILE_FORMAT = (FORMAT_NAME = ''' || file_format_name || ''')
    ON_ERROR = ''CONTINUE'';';
    
    EXECUTE IMMEDIATE sql_stmt;
    
    result := 'Partition ' || partition_column || '=' || partition_value || 
              ' loaded successfully. Rows: ' || SQLROWCOUNT;
    
    RETURN result;
END;
$$;