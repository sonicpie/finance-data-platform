# Finance Data Platform

A local prototype of a finance data platform: Terraform creates an S3 data lake on LocalStack, and a Python + DuckDB pipeline checks raw transactions and publishes daily spend per category.

## Quickstart

You need Docker and Make. Nothing else is installed on your machine.

```
make up        # start LocalStack, create buckets and roles, upload sample data, run the pipeline
make test      # unit tests for the quality rules
make lint      # terraform fmt -check and terraform validate
make pipeline  # run the pipeline again (the output does not change)
make down      # stop everything and delete local state
```

`make up` ends by printing the rejected rows and the curated metrics.

## How it works

```
seed_data/*.csv
      |  make seed
      v
s3://finance-data-landing/transactions/ingest_date=YYYY-MM-DD/transactions.csv
      |  make pipeline: quality gate
      |--- bad rows  ---> s3://finance-data-landing/quarantine/rejected_rows.parquet
      v
   good rows, totalled by day and category
      v
s3://finance-data-curated/daily_category_metrics/transaction_date=YYYY-MM-DD/*.parquet
```

### Part 1: infrastructure (`infrastructure/`)

- `modules/data_domain` creates a landing and a curated bucket for one domain, each with SSE-S3 encryption and a lifecycle policy (Standard-IA after 30 days, Glacier Instant Retrieval after 90, never deleted).
- `main.tf` calls the module once per domain (`finance`, `marketing`). Adding a domain means adding one name to the `domains` variable.
- `iam.tf` defines two roles: `data_engineer` (full S3 access to every domain's buckets) and `finance_analyst` (list and read on `finance-data-curated` only).

### Part 2: pipeline (`pipeline/`)

- `seed.py` uploads two days of sample transactions. They include a negative amount, a missing ID and a duplicated ID.
- `pipeline.py` is a plain Python script with four steps: load, validate, write quarantine, write curated.
- The quality rules are one SQL `CASE` statement. A row is rejected for the first rule it fails:

| Rule | Rejects |
| --- | --- |
| `missing_transaction_id` | ID is empty |
| `invalid_date` | `transaction_date` is not a date |
| `invalid_amount` | `amount` is not a number |
| `non_positive_amount` | `amount` is zero or negative |
| `duplicate_transaction_id` | ID appears more than once, in any file |

- Rejected rows go to a quarantine file in the landing bucket, with the reason. They never reach curated, which is the only bucket the analyst role can read.

## Trade-offs

| Decision | Alternative | Why |
| --- | --- | --- |
| Plain Python script as the runner | Prefect, Airflow, Dagster | Four steps that run in order don't need a scheduler yet. Each step is a function, so wrapping them in tasks later is a small change. |
| DuckDB | Polars, PySpark, dbt | Runs inside the Python process, reads and writes S3 Parquet directly, and the rules are plain SQL that would port to Spark or Athena. |
| Reprocess all of landing on every run | Process only the new file | It is the simplest way to be idempotent, and it catches a duplicate ID that arrives in a later file. The cost grows with the amount of data. |
| Reject every copy of a duplicated ID | Keep the first copy | The two copies can disagree on the amount and there is no way to know which is right. A missing transaction is noticed; a wrong total is not. |
| Read every CSV column as text, then `TRY_CAST` | Let DuckDB guess the types | One bad value becomes one rejected row instead of a failed run. |
| Amounts as `DECIMAL(18,2)` | Float | Float sums drift by fractions of a cent. |
| Partition curated by `transaction_date` | By ingest date, or by date and category | It is how analysts filter. A late row lands in the day it belongs to. Adding category would make many tiny files. |
| SSE-S3 | SSE-KMS | Meets the requirement with no keys to manage. |
| LocalStack pinned to 4.14 | Latest | Newer versions need an account and token. |
| Everything runs in containers | Install Terraform and Python locally | One command works on any machine with Docker. |

## Known limitations

- Free LocalStack creates the IAM roles but does not enforce them, and it accepts the encryption and lifecycle settings without acting on them.
- The pipeline deletes the curated folder and then rewrites it, so a reader could briefly see no data, and a failure between the two steps leaves curated empty until the next run.
- An amount with more than two decimal places is rounded, not rejected.
- One lifecycle rule is applied to both buckets. Curated is rewritten on every run, so its objects never age into cheaper storage.
- Terraform state is a local file.
- The tests cover the quality rules only; nothing tests the S3 reads and writes.

## What I would do next

1. **Orchestration:** wrap the steps in a Prefect flow for retries on S3 calls, scheduling and run history.
2. **Circuit breaker:** fail the run without publishing if more than, say, 10% of a new file is rejected, so a broken delivery can't quietly shrink the totals.
3. **Reconciliation:** check that rows read = rows published + rows quarantined, and log the counts.
4. **Safer publish:** write to a new location and switch over, or enable bucket versioning on curated, so a bad run can be rolled back.
5. **Incremental processing:** once landing is large, process only new files and keep a record of seen IDs.
6. **Security:** block public access on every bucket, add a security scanner (Trivy or tfsec) to `make lint`, and consider KMS keys per domain.
7. **Integration test:** run the whole pipeline against LocalStack and compare the output to known totals.
8. **Currency:** amounts are assumed to be in one currency; real data would need a currency column and conversion.
