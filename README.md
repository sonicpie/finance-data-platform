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

## Repository layout

```
part1_infrastructure/   Terraform: S3 buckets per data domain and IAM roles
part2_pipeline/         Python + DuckDB: seed script, pipeline, tests, sample data
docker-compose.yml      LocalStack, Terraform and pipeline containers
Makefile                the commands above
```

## How it works

```
part2_pipeline/seed_data/*.csv
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

### Part 1: infrastructure (`part1_infrastructure/`)

- `modules/data_domain` creates a landing and a curated bucket for one domain, each with SSE-S3 encryption and a lifecycle policy (Standard-IA after 30 days, Glacier Instant Retrieval after 90, never deleted).
- `main.tf` calls the module once per domain (`finance`, `marketing`). Adding a domain means adding one name to the `domains` variable.
- `iam.tf` defines two roles: `data_engineer` (full S3 access to every domain's buckets) and `finance_analyst` (list and read on `finance-data-curated` only).

### Part 2: pipeline (`part2_pipeline/`)

- `seed.py` uploads two days of sample transactions. They include a negative amount, a missing ID and a duplicated ID.
- `pipeline.py` is a plain Python script with four steps: load, validate, write quarantine, write curated.
- Every CSV column is read as text and converted with `TRY_CAST`, so a bad value in a well-formed file becomes one rejected row instead of a failed run.
- Amounts are `DECIMAL(18,2)`, never float, so totals are exact to the cent.
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

| Decision | Alternative | Reasoning and cost |
| --- | --- | --- |
| Plain Python script as the runner | Prefect, Airflow, Dagster | Adequate for four steps run by hand, but has no retries, scheduling, run history or dependencies between jobs. Each step is a function, so it maps directly onto an orchestrator task later. |
| DuckDB | Polars, PySpark, pandas | Simple to set up and simple to review (the quality rules are one SQL statement). The trade-off is that it runs on one machine; much larger data would need a distributed engine such as Spark, though the SQL would mostly carry over. |
| Reprocess all of landing on every run | Process only the new file | It is the simplest way to be idempotent, and it catches a duplicate ID that arrives in a later file. The cost grows with the amount of data. |
| Reject every copy of a duplicated ID | Keep the first, or the latest | Quarantined copies are visible and explained, while picking one could publish a wrong amount with no trace. The cost is that the transaction is missing from the totals until someone resolves it. |
| Partition curated by `transaction_date` | By `ingest_date` | Analysts filter by transaction date, and a late row lands in the day it belongs to. The cost is that published days can change: a late row adds to an earlier day, and a later duplicate removes a row from one. Partitioning by ingest date would make each load append-only, but that only pays off once the pipeline is incremental; today every run rewrites all of curated either way. |

## Known limitations

- Free LocalStack creates the IAM roles but does not enforce them, and it accepts the encryption and lifecycle settings without acting on them.
- The pipeline deletes the curated folder and then rewrites it, so a reader could briefly see no data, and a failure between the two steps leaves curated empty until the next run.
- An amount with more than two decimal places is rounded, not rejected.
- One lifecycle rule is applied to both buckets, and it does not fit how the prototype uses them. Curated is rewritten on every run, so its objects never age into cheaper storage. Landing does age, but the pipeline rereads all of it on every run, which would incur retrieval fees on real AWS. The rule suits landing only once processing is incremental.

## What I would do next

1. **Reconciliation:** check that every row is published or quarantined.
2. **Duplicates:** agree handling rules with the source, and MERGE in updates instead of rejecting every copy.
3. **Circuit breaker:** stop publishing when a delivery is mostly rejected.
4. **Currency:** support more than one currency.
5. **Orchestration:** move to Prefect or Airflow.
6. **Integration testing:** test on real AWS.
7. **Security:** block public access, scan the Terraform, use a KMS key per domain.
