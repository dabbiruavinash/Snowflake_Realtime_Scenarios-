CREATE OR REPLACE PROCEDURE CREATE_TABLE_VIEWS_PROCEDURE(
    source_schema STRING,
    view_schema STRING,
    table_prefix STRING DEFAULT 'VW_'
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    table_name STRING;
    view_name STRING;
    sql_stmt STRING;
    result STRING := '';
    c1 CURSOR FOR 
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = UPPER(source_schema)
        AND table_type = 'BASE TABLE';
BEGIN
    OPEN c1;
    LOOP
        FETCH c1 INTO table_name;
        IF (table_name IS NULL) THEN
            BREAK;
        END IF;
        
        view_name := table_prefix || table_name;
        
        -- Drop existing view if exists
        sql_stmt := 'DROP VIEW IF EXISTS ' || view_schema || '.' || view_name || ';';
        EXECUTE IMMEDIATE sql_stmt;
        
        -- Create view with all columns from table
        sql_stmt := '
        CREATE OR REPLACE VIEW ' || view_schema || '.' || view_name || ' AS
        SELECT * FROM ' || source_schema || '.' || table_name || ';';
        
        EXECUTE IMMEDIATE sql_stmt;
        
        result := result || 'Created view: ' || view_name || '\n';
    END LOOP;
    CLOSE c1;
    
    RETURN result;
END;
$$;