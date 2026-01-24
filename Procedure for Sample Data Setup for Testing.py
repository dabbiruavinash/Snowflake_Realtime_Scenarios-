CREATE OR REPLACE PROCEDURE SETUP_SAMPLE_DATA_PROCEDURE(
    source_schema STRING,
    target_schema STRING,
    sample_size INT DEFAULT 1000,
    table_name_pattern STRING DEFAULT '%'
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    table_name STRING;
    column_list STRING;
    sql_stmt STRING;
    result STRING := '';
    c1 CURSOR FOR 
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = UPPER(source_schema)
        AND table_type = 'BASE TABLE'
        AND table_name LIKE table_name_pattern;
BEGIN
    OPEN c1;
    LOOP
        FETCH c1 INTO table_name;
        IF (table_name IS NULL) THEN
            BREAK;
        END IF;
        
        -- Truncate target table first
        sql_stmt := 'TRUNCATE TABLE IF EXISTS ' || target_schema || '.' || table_name || ';';
        EXECUTE IMMEDIATE sql_stmt;
        
        -- Get column list
        sql_stmt := '
        SELECT LISTAGG(column_name, ', ') WITHIN GROUP (ORDER BY ordinal_position)
        FROM information_schema.columns
        WHERE table_schema = UPPER(''' || source_schema || ''')
        AND table_name = ''' || table_name || '''';
        
        EXECUTE IMMEDIATE sql_stmt INTO column_list;
        
        -- Insert sample data
        sql_stmt := '
        INSERT INTO ' || target_schema || '.' || table_name || ' (' || column_list || ')
        SELECT ' || column_list || '
        FROM ' || source_schema || '.' || table_name || '
        SAMPLE (' || sample_size || ' ROWS)';
        
        EXECUTE IMMEDIATE sql_stmt;
        
        result := result || 'Sample data created for: ' || table_name || ' - ' || SQLROWCOUNT || ' rows\n';
    END LOOP;
    CLOSE c1;
    
    RETURN result;
END;
$$;