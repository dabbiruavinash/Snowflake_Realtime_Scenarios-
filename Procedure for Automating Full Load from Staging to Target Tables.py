CREATE OR REPLACE PROCEDURE FULL_LOAD_PROCEDURE(
    staging_schema STRING,
    target_schema STRING,
    table_name_pattern STRING DEFAULT '%'
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    table_name STRING;
    sql_stmt STRING;
    result STRING := '';
    c1 CURSOR FOR 
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = UPPER(staging_schema)
        AND table_type = 'BASE TABLE'
        AND table_name LIKE table_name_pattern;
BEGIN
    OPEN c1;
    LOOP
        FETCH c1 INTO table_name;
        IF (table_name IS NULL) THEN
            BREAK;
        END IF;
        
        -- Truncate target table
        sql_stmt := 'TRUNCATE TABLE ' || target_schema || '.' || table_name || ';';
        EXECUTE IMMEDIATE sql_stmt;
        
        -- Insert data from staging
        sql_stmt := '
        INSERT INTO ' || target_schema || '.' || table_name || '
        SELECT * FROM ' || staging_schema || '.' || table_name || ';';
        
        EXECUTE IMMEDIATE sql_stmt;
        
        result := result || 'Loaded table: ' || table_name || ' - ' || SQLROWCOUNT || ' rows inserted\n';
    END LOOP;
    CLOSE c1;
    
    RETURN result;
END;
$$;