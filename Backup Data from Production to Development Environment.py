CREATE OR REPLACE PROCEDURE PROD_TO_DEV_BACKUP(
    prod_database STRING,
    prod_schema STRING,
    dev_database STRING,
    dev_schema STRING,
    backup_type STRING, -- 'FULL', 'INCREMENTAL', 'SCHEMA_ONLY'
    retention_days INT DEFAULT 30,
    compress_data BOOLEAN DEFAULT TRUE
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    table_name STRING;
    backup_timestamp STRING;
    backup_schema STRING;
    sql_stmt STRING;
    result STRING := '';
    c1 CURSOR FOR 
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_catalog = UPPER(prod_database)
        AND table_schema = UPPER(prod_schema)
        AND table_type = 'BASE TABLE';
BEGIN
    -- Create backup timestamp
    backup_timestamp := TO_CHAR(CURRENT_TIMESTAMP(), 'YYYYMMDD_HH24MISS');
    backup_schema := 'BACKUP_' || backup_timestamp;
    
    -- Create backup schema in dev
    sql_stmt := 'CREATE SCHEMA IF NOT EXISTS ' || dev_database || '.' || backup_schema || ';';
    EXECUTE IMMEDIATE sql_stmt;
    
    -- Create backup metadata table
    sql_stmt := '
    CREATE TABLE IF NOT EXISTS ' || dev_database || '.BACKUP_METADATA (
        backup_id STRING,
        backup_timestamp TIMESTAMP_NTZ,
        source_database STRING,
        source_schema STRING,
        target_database STRING,
        target_schema STRING,
        backup_type STRING,
        table_count NUMBER,
        total_rows NUMBER,
        total_size_mb NUMBER,
        backup_status STRING,
        created_by STRING
    );';
    EXECUTE IMMEDIATE sql_stmt;
    
    OPEN c1;
    LOOP
        FETCH c1 INTO table_name;
        IF (table_name IS NULL) THEN
            BREAK;
        END IF;
        
        CASE (UPPER(backup_type))
            WHEN 'FULL' THEN
                -- Create backup table with data
                sql_stmt := '
                CREATE OR REPLACE TABLE ' || dev_database || '.' || backup_schema || '.' || table_name || '
                CLONE ' || prod_database || '.' || prod_schema || '.' || table_name || ';';
                EXECUTE IMMEDIATE sql_stmt;
                
            WHEN 'INCREMENTAL' THEN
                -- Backup only changed data since last backup
                sql_stmt := '
                CREATE TABLE IF NOT EXISTS ' || dev_database || '.' || backup_schema || '.' || table_name || '
                AS SELECT * FROM ' || prod_database || '.' || prod_schema || '.' || table_name || '
                WHERE updated_at > COALESCE(
                    (SELECT MAX(updated_at) 
                     FROM ' || dev_database || '.' || dev_schema || '.' || table_name || '),
                    DATEADD(day, -7, CURRENT_TIMESTAMP())
                );';
                EXECUTE IMMEDIATE sql_stmt;
                
            WHEN 'SCHEMA_ONLY' THEN
                -- Backup only schema
                sql_stmt := '
                CREATE OR REPLACE TABLE ' || dev_database || '.' || backup_schema || '.' || table_name || '
                LIKE ' || prod_database || '.' || prod_schema || '.' || table_name || ';';
                EXECUTE IMMEDIATE sql_stmt;
                
        END CASE;
        
        -- Compress table if requested
        IF (compress_data) THEN
            sql_stmt := '
            ALTER TABLE ' || dev_database || '.' || backup_schema || '.' || table_name || '
            RECLUSTER;';
            EXECUTE IMMEDIATE sql_stmt;
        END IF;
        
        result := result || 'Backed up: ' || table_name || '\n';
    END LOOP;
    CLOSE c1;
    
    -- Calculate backup statistics
    sql_stmt := '
    INSERT INTO ' || dev_database || '.BACKUP_METADATA
    SELECT
        ''' || backup_timestamp || ''' as backup_id,
        CURRENT_TIMESTAMP() as backup_timestamp,
        ''' || prod_database || ''' as source_database,
        ''' || prod_schema || ''' as source_schema,
        ''' || dev_database || ''' as target_database,
        ''' || backup_schema || ''' as target_schema,
        ''' || backup_type || ''' as backup_type,
        COUNT(DISTINCT t.table_name) as table_count,
        SUM(t.row_count) as total_rows,
        SUM(t.bytes) / (1024*1024) as total_size_mb,
        ''COMPLETED'' as backup_status,
        CURRENT_USER() as created_by
    FROM information_schema.tables t
    WHERE t.table_schema = UPPER(''' || backup_schema || ''')
    AND t.table_catalog = UPPER(''' || dev_database || ''');';
    
    EXECUTE IMMEDIATE sql_stmt;
    
    -- Apply retention policy
    sql_stmt := '
    WITH old_backups AS (
        SELECT DISTINCT target_schema
        FROM ' || dev_database || '.BACKUP_METADATA
        WHERE backup_timestamp < DATEADD(day, -' || retention_days || ', CURRENT_TIMESTAMP())
    )
    SELECT target_schema FROM old_backups;';
    
    LET old_schemas RESULTSET := (EXECUTE IMMEDIATE sql_stmt);
    LET old_schema STRING;
    
    FOR old_schema IN old_schemas DO
        sql_stmt := 'DROP SCHEMA IF EXISTS ' || dev_database || '.' || old_schema || ' CASCADE;';
        EXECUTE IMMEDIATE sql_stmt;
        result := result || 'Cleaned up old backup: ' || old_schema || '\n';
    END FOR;
    
    -- Create restore procedure for this backup
    sql_stmt := '
    CREATE OR REPLACE PROCEDURE ' || dev_database || '.RESTORE_FROM_BACKUP_' || backup_timestamp || '(
        restore_schema STRING
    )
    RETURNS STRING
    LANGUAGE SQL
    AS
    $$
    DECLARE
        table_name STRING;
        sql_stmt STRING;
        result STRING := '''';
        c1 CURSOR FOR 
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = UPPER(''' || backup_schema || ''')
            AND table_catalog = UPPER(''' || dev_database || ''');
    BEGIN
        OPEN c1;
        LOOP
            FETCH c1 INTO table_name;
            IF (table_name IS NULL) THEN
                BREAK;
            END IF;
            
            -- Drop existing table if exists
            sql_stmt := ''DROP TABLE IF EXISTS '' || restore_schema || ''.'' || table_name || '';'';
            EXECUTE IMMEDIATE sql_stmt;
            
            -- Clone from backup
            sql_stmt := ''
            CREATE TABLE '' || restore_schema || ''.'' || table_name || ''
            CLONE ' || dev_database || '.' || backup_schema || '.' || table_name || ';'';
            EXECUTE IMMEDIATE sql_stmt;
            
            result := result || ''Restored: '' || table_name || ''\\n'';
        END LOOP;
        CLOSE c1;
        
        RETURN result;
    END;
    $$;';
    
    EXECUTE IMMEDIATE sql_stmt;
    
    result := 'Backup completed successfully!' || '\n' ||
              'Backup ID: ' || backup_timestamp || '\n' ||
              'Backup Schema: ' || dev_database || '.' || backup_schema || '\n' ||
              'Restore Procedure: RESTORE_FROM_BACKUP_' || backup_timestamp || '\n' ||
              result;
    
    RETURN result;
END;
$$;

-- Procedure for point-in-time restore
CREATE OR REPLACE PROCEDURE POINT_IN_TIME_RESTORE(
    target_database STRING,
    target_schema STRING,
    restore_timestamp TIMESTAMP_NTZ,
    include_data BOOLEAN DEFAULT TRUE
)
RETURNS STRING
LANGUAGE SQL
AS
$$
DECLARE
    backup_schema STRING;
    table_name STRING;
    sql_stmt STRING;
    result STRING := '';
    c1 CURSOR FOR 
        SELECT target_schema as backup_schema
        FROM BACKUP_METADATA
        WHERE backup_timestamp <= :restore_timestamp
        ORDER BY backup_timestamp DESC
        LIMIT 1;
BEGIN
    OPEN c1;
    FETCH c1 INTO backup_schema;
    CLOSE c1;
    
    IF (backup_schema IS NULL) THEN
        RETURN 'No backup found before the specified timestamp: ' || restore_timestamp;
    END IF;
    
    -- Get tables from backup
    sql_stmt := '
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = ''' || UPPER(backup_schema) || '''
    AND table_catalog = ''' || UPPER(target_database) || '''';
    
    LET table_cursor CURSOR FOR sql_stmt;
    OPEN table_cursor;
    LOOP
        FETCH table_cursor INTO table_name;
        IF (table_name IS NULL) THEN
            BREAK;
        END IF;
        
        IF (include_data) THEN
            -- Clone with data
            sql_stmt := '
            CREATE OR REPLACE TABLE ' || target_schema || '.' || table_name || '
            CLONE ' || target_database || '.' || backup_schema || '.' || table_name || ';';
        ELSE
            -- Clone schema only
            sql_stmt := '
            CREATE OR REPLACE TABLE ' || target_schema || '.' || table_name || '
            LIKE ' || target_database || '.' || backup_schema || '.' || table_name || ';';
        END IF;
        
        EXECUTE IMMEDIATE sql_stmt;
        result := result || 'Restored: ' || table_name || '\n';
    END LOOP;
    CLOSE table_cursor;
    
    RETURN 'Restore completed from backup: ' || backup_schema || '\n' || result;
END;
$$;