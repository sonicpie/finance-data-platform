"""Finance pipeline: read raw CSVs from landing, quarantine bad rows, publish daily metrics.

Steps:
1. load_landing      read every CSV in the landing bucket into a table
2. validate          label each row with the first quality rule it fails (or nothing)
3. write_quarantine  save the failed rows, with the reason, away from the curated bucket
4. write_curated     total the good rows by day and category, save as partitioned Parquet

Every run reprocesses all of landing and rewrites both outputs, so running it twice
gives the same result.
"""

import os

import boto3
import duckdb

LANDING = "s3://finance-data-landing/transactions/*/*.csv"
QUARANTINE = "s3://finance-data-landing/quarantine/rejected_rows.parquet"
CURATED_BUCKET = "finance-data-curated"
CURATED_FOLDER = "daily_category_metrics"


def connect():
    """Open an in-memory DuckDB that can read and write S3 on LocalStack."""
    endpoint = os.environ["AWS_ENDPOINT_URL"].removeprefix("http://")  # "localstack:4566"
    con = duckdb.connect()
    con.execute("LOAD httpfs")  # DuckDB's S3 extension, installed in the Dockerfile
    con.execute(f"""
        CREATE SECRET (
            TYPE s3,
            KEY_ID 'test',
            SECRET 'test',
            REGION 'us-east-1',
            ENDPOINT '{endpoint}',
            URL_STYLE 'path',
            USE_SSL false
        )
    """)
    return con


def load_landing(con):
    """Read every landing CSV into a table called `landing`.

    all_varchar reads every column as text, so a bad value can't crash the load;
    the rules below decide what is valid. hive_partitioning adds an ingest_date
    column taken from the folder name (ingest_date=2026-11-13).
    """
    con.execute(f"""
        CREATE TABLE landing AS
        SELECT * FROM read_csv('{LANDING}', header = true, all_varchar = true, hive_partitioning = true)
    """)


def validate(con):
    """Create `checked`: every landing row plus a rejection_reason (NULL if the row is good).

    CASE stops at the first match, so a row gets the first rule it fails.
    TRY_CAST returns NULL instead of an error when a value can't be converted.
    The last rule counts how many rows share each transaction_id; every copy of
    a duplicated ID is rejected, because we can't tell which one is right.
    """
    con.execute("""
        CREATE TABLE checked AS
        SELECT
            *,
            CASE
                WHEN transaction_id IS NULL OR trim(transaction_id) = '' THEN 'missing_transaction_id'
                WHEN TRY_CAST(transaction_date AS DATE) IS NULL THEN 'invalid_date'
                WHEN TRY_CAST(amount AS DECIMAL(18, 2)) IS NULL THEN 'invalid_amount'
                WHEN TRY_CAST(amount AS DECIMAL(18, 2)) <= 0 THEN 'non_positive_amount'
                WHEN COUNT(*) OVER (PARTITION BY transaction_id) > 1 THEN 'duplicate_transaction_id'
            END AS rejection_reason
        FROM landing
    """)


def write_quarantine(con):
    """Save the rejected rows as one Parquet file. Each run replaces the file."""
    con.execute(f"""
        COPY (SELECT * FROM checked WHERE rejection_reason IS NOT NULL)
        TO '{QUARANTINE}' (FORMAT parquet)
    """)


def write_curated(con):
    """Total the good rows by day and category; write one folder per transaction_date."""
    # Delete the old output first. DuckDB can't replace a whole folder on S3,
    # so without this a re-run could leave stale files behind.
    boto3.resource("s3").Bucket(CURATED_BUCKET).objects.filter(Prefix=CURATED_FOLDER).delete()

    # Money is DECIMAL, never float, so totals are exact to the cent.
    con.execute(f"""
        COPY (
            SELECT
                CAST(transaction_date AS DATE) AS transaction_date,
                category,
                SUM(CAST(amount AS DECIMAL(18, 2))) AS total_spend,
                COUNT(*) AS transaction_count
            FROM checked
            WHERE rejection_reason IS NULL
            GROUP BY transaction_date, category
        )
        TO 's3://{CURATED_BUCKET}/{CURATED_FOLDER}' (FORMAT parquet, PARTITION_BY (transaction_date))
    """)


def main():
    con = connect()
    load_landing(con)
    validate(con)

    print("Rejected rows:")
    con.sql("SELECT * FROM checked WHERE rejection_reason IS NOT NULL ORDER BY ingest_date").show()

    write_quarantine(con)
    write_curated(con)

    print("Curated daily category metrics:")
    con.sql(f"""
        SELECT transaction_date, category, total_spend, transaction_count
        FROM read_parquet('s3://{CURATED_BUCKET}/{CURATED_FOLDER}/*/*.parquet', hive_partitioning = true)
        ORDER BY transaction_date, category
    """).show()


if __name__ == "__main__":
    main()