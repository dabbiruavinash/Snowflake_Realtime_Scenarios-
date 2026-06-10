👉 If a client shares a file in AWS S3:
How would you load only valid records into the target table?
How would you identify and separate invalid (bad) records?
Most importantly, how would you send those bad records back to the client for correction in a fully automated way?

Step 1: Load Everything (Raw Landing)
First, load the raw S3 file into a landing table where every column is a VARIANT or a generic VARCHAR. This ensures the load never fails due to data type mismatches .

-- Create a raw landing table
CREATE OR REPLACE TABLE RAW_DATA (
    raw_record VARIANT,  -- For JSON/Parquet, or use individual VARCHAR columns for CSV
    file_name STRING,
    row_number INT
);

-- Copy from S3
COPY INTO RAW_DATA (raw_record)
FROM 's3://client-bucket/incoming/'
FILE_FORMAT = (TYPE = JSON) 
ON_ERROR = 'CONTINUE'; -- This ensures the whole pipeline doesn't stop

-------

Step 2: Identify & Separate Bad Records (The "Validation" Phase)
This is the critical step they are testing. You use a MERGE or INSERT statement with TRY_CAST to split the data into Final Table and Error Table in a single transaction.

-- Table for good, clean data
CREATE OR REPLACE TABLE TARGET_TABLE (
    id INT, name STRING, amount DECIMAL(10,2)
);

-- Table for bad records (includes the reason for rejection)
CREATE OR REPLACE TABLE BAD_RECORDS_TABLE (
    raw_data_variant VARIANT,
    rejection_reason STRING,
    file_name STRING,
    detected_timestamp TIMESTAMP
);

-- The Validation Logic: Split good from bad
BEGIN;
    -- Insert valid records (where casting succeeds)
    INSERT INTO TARGET_TABLE (id, name, amount)
    SELECT 
        raw_record:id::INT,
        raw_record:name::STRING,
        raw_record:amount::DECIMAL(10,2)
    FROM RAW_DATA
    WHERE 
        TRY_CAST(raw_record:id AS INT) IS NOT NULL 
        AND TRY_CAST(raw_record:amount AS DECIMAL) IS NOT NULL;

    -- Insert invalid records (where casting fails)
    INSERT INTO BAD_RECORDS_TABLE (raw_data_variant, rejection_reason)
    SELECT 
        raw_record,
        CASE 
            WHEN TRY_CAST(raw_record:id AS INT) IS NULL THEN 'Invalid ID format'
            WHEN TRY_CAST(raw_record:amount AS DECIMAL) IS NULL THEN 'Invalid Amount'
            ELSE 'Schema Mismatch'
        END
    FROM RAW_DATA
    WHERE 
        TRY_CAST(raw_record:id AS INT) IS NULL 
        OR TRY_CAST(raw_record:amount AS DECIMAL) IS NULL;
COMMIT;

--------------
Step 3: Automating the Return to Client (The "Ejection")
To send the bad records back automatically, you cannot use a standard COPY because the client needs a file. You need a task that runs after validation and unloads the error table to S3.

-- Create a stage pointing to the client's "Error" folder
CREATE OR REPLACE STAGE client_error_stage
    URL = 's3://client-bucket/errors/'
    CREDENTIALS = (AWS_KEY_ID = '...' AWS_SECRET_KEY = '...');

-- Create a Task to run every hour, or trigger via Snowpipe
CREATE OR REPLACE TASK return_bad_files
    WAREHOUSE = my_wh
    SCHEDULE = '1 HOUR'
WHEN
    SYSTEM$STREAM_HAS_DATA('BAD_RECORDS_STREAM') -- Assumes a stream on the error table
AS
    COPY INTO @client_error_stage/bad_records_$$.csv
    FROM (
        SELECT rejection_reason, raw_data_variant::STRING 
        FROM BAD_RECORDS_TABLE 
        WHERE exported_flag = FALSE
    )
    FILE_FORMAT = (TYPE = CSV COMPRESSION = NONE)
    SINGLE = FALSE
    HEADER = TRUE;

-- Resume the task
ALTER TASK return_bad_files RESUME;
