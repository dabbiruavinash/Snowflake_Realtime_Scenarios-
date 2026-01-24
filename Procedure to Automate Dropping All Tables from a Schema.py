CREATE OR REPLACE PROCEDURE DROP_ALL_TABLES_PROCEDURE(
    schema_name STRING,
    exclude_pattern STRING DEFAULT NULL
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
        WHERE table_schema = UPPER(schema_name)
        AND table_type = 'BASE TABLE'
        AND (exclude_pattern IS NULL OR table_name NOT LIKE exclude_pattern);
BEGIN
    OPEN c1;
    LOOP
        FETCH c1 INTO table_name;
        IF (table_name IS NULL) THEN
            BREAK;
        END IF;
        
        sql_stmt := 'DROP TABLE IF EXISTS ' || schema_name || '.' || table_name || ';';
        EXECUTE IMMEDIATE sql_stmt;
        
        result := result || 'Dropped table: ' || table_name || '\n';
    END LOOP;
    CLOSE c1;
    
    RETURN result || 'All tables dropped from schema: ' || schema_name;
END;
$$;