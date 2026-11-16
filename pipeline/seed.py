"""Upload the sample CSV files in seed_data/ to the landing bucket.

Each file is one day's delivery, named after the day it arrived (its ingest date):
seed_data/2026-11-13.csv -> s3://finance-data-landing/transactions/ingest_date=2026-11-13/transactions.csv

The files contain bad rows on purpose, for the quality gate to catch:
- 2026-11-13: a negative amount (TXN-1009) and a row with no transaction_id.
- 2026-11-14: TXN-1001 again with a different amount (a duplicate of a row from the 13th).
"""

from pathlib import Path

import boto3

# boto3 reads the LocalStack address from the AWS_ENDPOINT_URL environment variable.
s3 = boto3.client("s3")

for csv_file in sorted(Path("seed_data").glob("*.csv")):
    ingest_date = csv_file.stem  # file name without ".csv"
    key = f"transactions/ingest_date={ingest_date}/transactions.csv"
    s3.upload_file(str(csv_file), "finance-data-landing", key)
    print(f"Uploaded {csv_file} to s3://finance-data-landing/{key}")
