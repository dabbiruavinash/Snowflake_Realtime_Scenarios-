CREATE OR REPLACE PROCEDURE MIGRATE_VIEWS_PROCEDURE(
    source_db STRING,
    source_schema STRING,
    target_db STRING,
    target_schema STRING,
    view_name_pattern STRING DEFAULT '%'
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    create_ddl STRING;
    view_name STRING;
    sql_stmt STRING;
    result STRING := '';
    c1 CURSOR FOR 
        SELECT table_name 
        FROM information_schema.views 
        WHERE table_catalog = UPPER(source_db)
        AND table_schema = UPPER(source_schema)
        AND table_name LIKE view_name_pattern;
BEGIN
    OPEN c1;
    LOOP
        FETCH c1 INTO view_name;
        IF (view_name IS NULL) THEN
            BREAK;
        END IF;
        
        -- Get the CREATE VIEW DDL
        sql_stmt := 'SELECT GET_DDL(''VIEW'', ''' || source_db || '.' || source_schema || '.' || view_name || ''')';
        EXECUTE IMMEDIATE sql_stmt INTO create_ddl;
        
        -- Replace source database/schema with target
        create_ddl := REPLACE(create_ddl, source_db || '.' || source_schema, target_db || '.' || target_schema);
        
        -- Execute the modified DDL
        EXECUTE IMMEDIATE create_ddl;
        
        result := result || 'Created view: ' || target_db || '.' || target_schema || '.' || view_name || '\n';
    END LOOP;
    CLOSE c1;
    
    RETURN result;
END;
$$;