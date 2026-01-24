CREATE OR REPLACE PROCEDURE MIGRATE_STORED_PROCS_PROCEDURE(
    source_db STRING,
    source_schema STRING,
    target_db STRING,
    target_schema STRING
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    proc_ddl STRING;
    proc_name STRING;
    proc_type STRING;
    sql_stmt STRING;
    result STRING := '';
    c1 CURSOR FOR 
        SELECT procedure_name, procedure_type
        FROM information_schema.procedures
        WHERE procedure_catalog = UPPER(source_db)
        AND procedure_schema = UPPER(source_schema);
BEGIN
    OPEN c1;
    LOOP
        FETCH c1 INTO proc_name, proc_type;
        IF (proc_name IS NULL) THEN
            BREAK;
        END IF;
        
        -- Get the CREATE PROCEDURE DDL
        sql_stmt := 'SELECT GET_DDL(''PROCEDURE'', ''' || source_db || '.' || source_schema || '.' || proc_name || ''')';
        EXECUTE IMMEDIATE sql_stmt INTO proc_ddl;
        
        -- Replace source database/schema with target
        proc_ddl := REPLACE(proc_ddl, source_db || '.' || source_schema, target_db || '.' || target_schema);
        
        -- Drop if exists and recreate
        sql_stmt := 'DROP ' || proc_type || ' IF EXISTS ' || target_db || '.' || target_schema || '.' || proc_name || ';';
        BEGIN
            EXECUTE IMMEDIATE sql_stmt;
        EXCEPTION
            WHEN OTHER THEN
                -- Continue if drop fails
                NULL;
        END;
        
        -- Create the procedure
        EXECUTE IMMEDIATE proc_ddl;
        
        result := result || 'Created ' || LOWER(proc_type) || ': ' || proc_name || '\n';
    END LOOP;
    CLOSE c1;
    
    RETURN result;
END;
$$;