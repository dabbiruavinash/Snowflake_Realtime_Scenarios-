CREATE OR REPLACE PROCEDURE MIGRATE_TABLE_DDL_PROCEDURE(
    source_db STRING,
    source_schema STRING,
    target_db STRING,
    target_schema STRING,
    table_name_pattern STRING DEFAULT '%'
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    create_ddl STRING;
    table_name STRING;
    sql_stmt STRING;
    result STRING := '';
    c1 CURSOR FOR 
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_catalog = UPPER(source_db)
        AND table_schema = UPPER(source_schema)
        AND table_type = 'BASE TABLE'
        AND table_name LIKE table_name_pattern;
BEGIN
    OPEN c1;
    LOOP
        FETCH c1 INTO table_name;
        IF (table_name IS NULL) THEN
            BREAK;
        END IF;
        
        -- Get the CREATE TABLE DDL
        sql_stmt := 'SELECT GET_DDL(''TABLE'', ''' || source_db || '.' || source_schema || '.' || table_name || ''')';
        EXECUTE IMMEDIATE sql_stmt INTO create_ddl;
        
        -- Replace source database/schema with target
        create_ddl := REPLACE(create_ddl, source_db || '.' || source_schema, target_db || '.' || target_schema);
        
        -- Execute the modified DDL
        EXECUTE IMMEDIATE create_ddl;
        
        result := result || 'Created table: ' || target_db || '.' || target_schema || '.' || table_name || '\n';
    END LOOP;
    CLOSE c1;
    
    RETURN result;
END;
$$;