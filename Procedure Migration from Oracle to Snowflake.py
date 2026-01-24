CREATE OR REPLACE PROCEDURE MIGRATE_ORACLE_TO_SNOWFLAKE(
    oracle_connection_name STRING,
    snowflake_schema STRING,
    object_type STRING, -- 'PROCEDURE', 'FUNCTION', 'TABLE', 'VIEW'
    object_name_pattern STRING DEFAULT '%',
    execute_test BOOLEAN DEFAULT FALSE
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    oracle_ddl STRING;
    snowflake_ddl STRING;
    obj_name STRING;
    migration_log STRING := '';
    sql_stmt STRING;
    c1 CURSOR FOR 
        SELECT object_name
        FROM information_schema.ora_objects
        WHERE object_type = :object_type
        AND object_name LIKE :object_name_pattern;
BEGIN
    -- Create migration log table
    EXECUTE IMMEDIATE '
    CREATE TABLE IF NOT EXISTS ORACLE_MIGRATION_LOG (
        migration_id NUMBER AUTOINCREMENT,
        migration_timestamp TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
        object_type STRING,
        object_name STRING,
        oracle_ddl CLOB,
        snowflake_ddl CLOB,
        conversion_notes STRING,
        migration_status STRING,
        error_message STRING
    );';
    
    -- Open cursor based on object type
    CASE (UPPER(object_type))
        WHEN 'PROCEDURE' THEN
            -- Get Oracle procedures
            sql_stmt := '
            SELECT procedure_name
            FROM information_schema.ora_procedures
            WHERE procedure_name LIKE ''' || object_name_pattern || '''
            AND connection_name = ''' || oracle_connection_name || '''';
            
            LET proc_cursor CURSOR FOR sql_stmt;
            OPEN proc_cursor;
            LOOP
                FETCH proc_cursor INTO obj_name;
                IF (obj_name IS NULL) THEN
                    BREAK;
                END IF;
                
                -- Get Oracle procedure DDL
                sql_stmt := '
                SELECT GET_ORACLE_DDL(''PROCEDURE'', ''' || obj_name || ''', ''' || oracle_connection_name || ''')';
                EXECUTE IMMEDIATE sql_stmt INTO oracle_ddl;
                
                -- Convert to Snowflake syntax
                snowflake_ddl := CONVERT_ORACLE_TO_SNOWFLAKE(oracle_ddl, 'PROCEDURE');
                
                -- Log migration
                sql_stmt := '
                INSERT INTO ORACLE_MIGRATION_LOG 
                (object_type, object_name, oracle_ddl, snowflake_ddl, migration_status)
                VALUES (''PROCEDURE'', ''' || obj_name || ''', 
                        ''' || REPLACE(oracle_ddl, '''', '''''') || ''',
                        ''' || REPLACE(snowflake_ddl, '''', '''''') || ''',
                        ''CONVERTED'');';
                EXECUTE IMMEDIATE sql_stmt;
                
                -- Execute in Snowflake if requested
                IF (execute_test) THEN
                    BEGIN
                        EXECUTE IMMEDIATE snowflake_ddl;
                        sql_stmt := '
                        UPDATE ORACLE_MIGRATION_LOG 
                        SET migration_status = ''EXECUTED''
                        WHERE object_name = ''' || obj_name || '''
                        AND migration_status = ''CONVERTED'';';
                        EXECUTE IMMEDIATE sql_stmt;
                    EXCEPTION
                        WHEN OTHER THEN
                            sql_stmt := '
                            UPDATE ORACLE_MIGRATION_LOG 
                            SET migration_status = ''FAILED'',
                                error_message = ''' || SQLERRM || '''
                            WHERE object_name = ''' || obj_name || ''';';
                            EXECUTE IMMEDIATE sql_stmt;
                    END;
                END IF;
                
                migration_log := migration_log || 'Migrated procedure: ' || obj_name || '\n';
            END LOOP;
            CLOSE proc_cursor;
            
        WHEN 'FUNCTION' THEN
            -- Similar logic for functions
            migration_log := migration_log || 'Function migration logic...\n';
            
        WHEN 'TABLE' THEN
            -- Table migration with data
            migration_log := MIGRATE_ORACLE_TABLES(oracle_connection_name, snowflake_schema, object_name_pattern);
            
        WHEN 'VIEW' THEN
            -- View migration
            migration_log := MIGRATE_ORACLE_VIEWS(oracle_connection_name, snowflake_schema, object_name_pattern);
            
        ELSE
            migration_log := 'Unsupported object type: ' || object_type;
    END CASE;
    
    RETURN migration_log;
END;
$$;

-- Helper function for Oracle to Snowflake syntax conversion
CREATE OR REPLACE FUNCTION CONVERT_ORACLE_TO_SNOWFLAKE(
    oracle_code STRING,
    object_type STRING
)
RETURNS STRING
LANGUAGE SQL
AS
$$
    -- Replace Oracle-specific syntax with Snowflake equivalents
    LET converted STRING := oracle_code;
    
    -- Replace data types
    converted := REPLACE(converted, 'VARCHAR2', 'VARCHAR');
    converted := REPLACE(converted, 'NUMBER(', 'DECIMAL(');
    converted := REPLACE(converted, 'DATE', 'TIMESTAMP_NTZ');
    converted := REPLACE(converted, 'CLOB', 'STRING');
    converted := REPLACE(converted, 'BLOB', 'BINARY');
    
    -- Replace PL/SQL specific syntax
    converted := REGEXP_REPLACE(converted, 'IS\\s+BEGIN', 'AS\nBEGIN');
    converted := REGEXP_REPLACE(converted, 'END\\s+[^;]+;', 'END;');
    
    -- Replace Oracle functions
    converted := REPLACE(converted, 'SYSDATE', 'CURRENT_TIMESTAMP()');
    converted := REPLACE(converted, 'NVL(', 'COALESCE(');
    converted := REPLACE(converted, 'TO_CHAR(', 'TO_CHAR('); -- Same in Snowflake
    converted := REPLACE(converted, 'TO_DATE(', 'TO_DATE('); -- Same in Snowflake
    
    -- Remove Oracle-specific pragmas and hints
    converted := REGEXP_REPLACE(converted, 'PRAGMA\\s+[^;]+;', '');
    converted := REGEXP_REPLACE(converted, '/\\*\\+[^\\*]+\\*/', '');
    
    -- Add Snowflake-specific wrapper if needed
    IF (object_type = 'PROCEDURE') THEN
        converted := 'CREATE OR REPLACE PROCEDURE ' || converted;
    ELSIF (object_type = 'FUNCTION') THEN
        converted := 'CREATE OR REPLACE FUNCTION ' || converted;
    END IF;
    
    RETURN converted;
$$;

-- Procedure to migrate Oracle tables with data
CREATE OR REPLACE PROCEDURE MIGRATE_ORACLE_TABLES(
    oracle_connection STRING,
    snowflake_schema STRING,
    table_pattern STRING
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    table_name STRING;
    create_ddl STRING;
    migration_log STRING := '';
    sql_stmt STRING;
    c1 CURSOR FOR 
        SELECT table_name
        FROM information_schema.ora_tables
        WHERE table_name LIKE :table_pattern
        AND connection_name = :oracle_connection;
BEGIN
    OPEN c1;
    LOOP
        FETCH c1 INTO table_name;
        IF (table_name IS NULL) THEN
            BREAK;
        END IF;
        
        -- Get Oracle table DDL
        sql_stmt := '
        SELECT GET_ORACLE_DDL(''TABLE'', ''' || table_name || ''', ''' || oracle_connection || ''')';
        EXECUTE IMMEDIATE sql_stmt INTO create_ddl;
        
        -- Convert to Snowflake DDL
        create_ddl := CONVERT_ORACLE_TO_SNOWFLAKE(create_ddl, 'TABLE');
        
        -- Create table in Snowflake
        EXECUTE IMMEDIATE create_ddl;
        
        -- Create external stage for data transfer
        sql_stmt := '
        CREATE OR REPLACE STAGE ORA_' || table_name || '_STAGE
        FILE_FORMAT = (TYPE = ''CSV'', FIELD_DELIMITER = ''|'', 
                      SKIP_HEADER = 1, NULL_IF = (''NULL''));';
        EXECUTE IMMEDIATE sql_stmt;
        
        -- Export data from Oracle to stage (requires Oracle integration)
        sql_stmt := '
        COPY INTO @ORA_' || table_name || '_STAGE
        FROM ' || oracle_connection || '.' || table_name || '
        FILE_FORMAT = (TYPE = ''CSV'', FIELD_DELIMITER = ''|'');';
        EXECUTE IMMEDIATE sql_stmt;
        
        -- Load data into Snowflake table
        sql_stmt := '
        COPY INTO ' || snowflake_schema || '.' || table_name || '
        FROM @ORA_' || table_name || '_STAGE
        FILE_FORMAT = (TYPE = ''CSV'', FIELD_DELIMITER = ''|'', 
                      SKIP_HEADER = 1, NULL_IF = (''NULL''));';
        EXECUTE IMMEDIATE sql_stmt;
        
        migration_log := migration_log || 'Migrated table: ' || table_name || 
                         ' - Rows: ' || SQLROWCOUNT || '\n';
    END LOOP;
    CLOSE c1;
    
    RETURN migration_log;
END;
$$;