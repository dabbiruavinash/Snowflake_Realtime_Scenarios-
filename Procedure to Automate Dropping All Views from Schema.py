CREATE OR REPLACE PROCEDURE DROP_ALL_VIEWS_PROCEDURE(
    schema_name STRING,
    exclude_pattern STRING DEFAULT NULL
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    view_name STRING;
    sql_stmt STRING;
    result STRING := '';
    c1 CURSOR FOR 
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = UPPER(schema_name)
        AND table_type = 'VIEW'
        AND (exclude_pattern IS NULL OR table_name NOT LIKE exclude_pattern);
BEGIN
    OPEN c1;
    LOOP
        FETCH c1 INTO view_name;
        IF (view_name IS NULL) THEN
            BREAK;
        END IF;
        
        sql_stmt := 'DROP VIEW IF EXISTS ' || schema_name || '.' || view_name || ';';
        EXECUTE IMMEDIATE sql_stmt;
        
        result := result || 'Dropped view: ' || view_name || '\n';
    END LOOP;
    CLOSE c1;
    
    RETURN result || 'All views dropped from schema: ' || schema_name;
END;
$$;