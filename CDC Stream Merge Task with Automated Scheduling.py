CREATE OR REPLACE PROCEDURE CREATE_CDC_MERGE_TASK(
    source_table STRING,
    target_table STRING,
    stream_name STRING,
    task_name STRING,
    warehouse_name STRING,
    schedule_expression STRING,
    merge_key STRING,
    cdc_columns STRING DEFAULT NULL
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    create_stream_sql STRING;
    create_task_sql STRING;
    merge_sql STRING;
    result STRING;
BEGIN
    -- Create stream on source table if not exists
    create_stream_sql := '
    CREATE OR REPLACE STREAM ' || stream_name || ' 
    ON TABLE ' || source_table || '
    APPEND_ONLY = TRUE
    SHOW_INITIAL_ROWS = TRUE;';
    
    EXECUTE IMMEDIATE create_stream_sql;
    
    -- Build dynamic merge statement
    IF (cdc_columns IS NULL) THEN
        -- Get column list excluding metadata columns
        LET col_list STRING;
        LET set_clause STRING;
        
        SELECT 
            LISTAGG(column_name, ', ') WITHIN GROUP (ORDER BY ordinal_position),
            LISTAGG('target.' || column_name || ' = source.' || column_name, ', ') 
            WITHIN GROUP (ORDER BY ordinal_position)
        INTO :col_list, :set_clause
        FROM information_schema.columns 
        WHERE table_name = UPPER(SPLIT_PART(source_table, '.', -1))
        AND column_name NOT IN ('METADATA$ACTION', 'METADATA$ISUPDATE', 'METADATA$ROW_ID');
    ELSE
        -- Use provided columns
        LET col_array ARRAY := SPLIT(cdc_columns, ',');
        LET col_list STRING := ARRAY_TO_STRING(col_array, ', ');
        
        LET set_parts ARRAY;
        FOR i IN 1 TO ARRAY_SIZE(col_array) DO
            set_parts := ARRAY_APPEND(set_parts, 
                'target.' || TRIM(col_array[i]) || ' = source.' || TRIM(col_array[i]));
        END FOR;
        
        LET set_clause STRING := ARRAY_TO_STRING(set_parts, ', ');
    END IF;
    
    -- Create merge statement
    merge_sql := '
    MERGE INTO ' || target_table || ' AS target
    USING ' || stream_name || ' AS source
    ON target.' || merge_key || ' = source.' || merge_key || '
    WHEN MATCHED AND source.METADATA$ACTION = ''DELETE'' THEN
        DELETE
    WHEN MATCHED AND source.METADATA$ACTION = ''INSERT'' THEN
        UPDATE SET ' || set_clause || '
    WHEN MATCHED AND source.METADATA$ACTION = ''UPDATE'' THEN
        UPDATE SET ' || set_clause || '
    WHEN NOT MATCHED AND source.METADATA$ACTION = ''INSERT'' THEN
        INSERT (' || merge_key || ', ' || col_list || ')
        VALUES (source.' || merge_key || ', source.' || col_list || ');';
    
    -- Create automated task
    create_task_sql := '
    CREATE OR REPLACE TASK ' || task_name || '
    WAREHOUSE = ' || warehouse_name || '
    SCHEDULE = ''' || schedule_expression || '''
    AS
    BEGIN
        ' || merge_sql || '
        
        -- Reset stream after successful merge
        ALTER STREAM ' || stream_name || ' SET OFFSET = LATEST_OFFSET();
        
        -- Log successful execution
        INSERT INTO CDC_MERGE_LOG 
        VALUES (CURRENT_TIMESTAMP(), ''' || task_name || ''', 
                ''' || source_table || ''', ''' || target_table || ''',
                ''SUCCESS'', SQLROWCOUNT);
    EXCEPTION
        WHEN OTHER THEN
            INSERT INTO CDC_MERGE_LOG 
            VALUES (CURRENT_TIMESTAMP(), ''' || task_name || ''', 
                    ''' || source_table || ''', ''' || target_table || ''',
                    ''FAILED: '' || SQLERRM, 0);
            RAISE;
    END;';
    
    EXECUTE IMMEDIATE create_task_sql;
    
    -- Create log table if not exists
    EXECUTE IMMEDIATE '
    CREATE TABLE IF NOT EXISTS CDC_MERGE_LOG (
        execution_time TIMESTAMP_NTZ,
        task_name STRING,
        source_table STRING,
        target_table STRING,
        status STRING,
        rows_affected NUMBER
    );';
    
    -- Resume the task
    EXECUTE IMMEDIATE 'ALTER TASK ' || task_name || ' RESUME;';
    
    result := 'CDC merge task created successfully:' || '\n' ||
              'Task Name: ' || task_name || '\n' ||
              'Schedule: ' || schedule_expression || '\n' ||
              'Source: ' || source_table || '\n' ||
              'Target: ' || target_table || '\n' ||
              'Stream: ' || stream_name;
    
    RETURN result;
END;
$$;

-- Procedure to monitor CDC tasks
CREATE OR REPLACE PROCEDURE MONITOR_CDC_TASKS()
RETURNS TABLE(
    task_name STRING,
    source_table STRING,
    target_table STRING,
    last_run TIMESTAMP_NTZ,
    status STRING,
    rows_processed NUMBER,
    lag_minutes NUMBER
)
LANGUAGE SQL
AS
$$
DECLARE
    res RESULTSET;
BEGIN
    res := (EXECUTE IMMEDIATE '
    WITH task_history AS (
        SELECT 
            name as task_name,
            database_name,
            schema_name,
            query_text,
            completed_time,
            state,
            error_code,
            error_message
        FROM table(information_schema.task_history())
        WHERE scheduled_time >= DATEADD(hour, -24, CURRENT_TIMESTAMP())
    ),
    stream_status AS (
        SELECT
            REPLACE(s.table_name, ''_STREAM'', '''') as table_name,
            s.stream_name,
            DATEDIFF(minute, s.last_refreshed, CURRENT_TIMESTAMP()) as lag_minutes
        FROM information_schema.streams s
    )
    SELECT 
        th.task_name,
        REGEXP_SUBSTR(th.query_text, ''USING\\\\s+([^\\\\s]+)\\\\s+AS'', 1, 1, ''e'') as source_table,
        REGEXP_SUBSTR(th.query_text, ''MERGE\\\\s+INTO\\\\s+([^\\\\s]+)\\\\s+AS'', 1, 1, ''e'') as target_table,
        MAX(th.completed_time) as last_run,
        MAX(CASE WHEN th.state = ''SUCCEEDED'' THEN ''SUCCESS'' 
                WHEN th.state = ''FAILED'' THEN ''FAILED'' 
                ELSE th.state END) as status,
        COALESCE(MAX(l.rows_affected), 0) as rows_processed,
        COALESCE(MIN(ss.lag_minutes), 0) as lag_minutes
    FROM task_history th
    LEFT JOIN CDC_MERGE_LOG l 
        ON th.task_name = l.task_name 
        AND l.execution_time >= DATEADD(hour, -1, th.completed_time)
    LEFT JOIN stream_status ss 
        ON ss.table_name = REGEXP_SUBSTR(th.query_text, ''ON\\\\s+TABLE\\\\s+([^\\\\s]+)'', 1, 1, ''e'')
    WHERE th.task_name LIKE ''%CDC%'' OR th.task_name LIKE ''%MERGE%''
    GROUP BY th.task_name, th.query_text
    ORDER BY last_run DESC;');
    
    RETURN TABLE(res);
END;
$$;