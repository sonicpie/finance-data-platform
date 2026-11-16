TERRAFORM := docker compose run --rm terraform
PIPELINE  := docker compose run --rm --build pipeline

.PHONY: up infra lint seed pipeline test down

# Everything from a fresh clone: start LocalStack, create the buckets, load data, run the pipeline.
up:
	docker compose up -d --wait localstack
	$(MAKE) infra seed pipeline	

# Create the buckets and IAM roles in LocalStack.
infra:
	$(TERRAFORM) init -input=false
	$(TERRAFORM) apply -input=false -auto-approve

# Check Terraform formatting and syntax. Does not need LocalStack.
lint:
	$(TERRAFORM) fmt -check -recursive
	$(TERRAFORM) init -backend=false -input=false
	$(TERRAFORM) validate

# Upload the sample CSV files to the landing bucket.
seed:
	$(PIPELINE) python seed.py

# Quality gate, quarantine and curated output.
pipeline:
	$(PIPELINE) python pipeline.py

# Unit tests for the quality rules. Does not need LocalStack.
test:
	$(PIPELINE) pytest -q

# Stop everything and delete local Terraform state.
down:
	docker compose down -v --remove-orphans
	rm -rf infrastructure/.terraform infrastructure/terraform.tfstate*