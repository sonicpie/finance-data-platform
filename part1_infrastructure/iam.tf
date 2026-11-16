# Two roles. Note: free LocalStack creates these but does not enforce them.

locals {
  # Every bucket ARN from every domain.
  all_bucket_arns = flatten([for d in module.data_domain : values(d.bucket_arns)])

  finance_curated_arn = module.data_domain["finance"].bucket_arns["curated"]
}

# Who may use the roles: anyone in this account (000000000000 is LocalStack's account).
data "aws_iam_policy_document" "trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::000000000000:root"]
    }
  }
}

# data_engineer: full S3 access to every domain's buckets.
data "aws_iam_policy_document" "data_engineer" {
  statement {
    actions = ["s3:*"]
    resources = concat(
      local.all_bucket_arns,                           # the buckets
      [for arn in local.all_bucket_arns : "${arn}/*"], # the objects inside them
    )
  }
}

resource "aws_iam_role" "data_engineer" {
  name               = "data_engineer"
  assume_role_policy = data.aws_iam_policy_document.trust.json
}

resource "aws_iam_role_policy" "data_engineer" {
  name   = "s3-full-access"
  role   = aws_iam_role.data_engineer.id
  policy = data.aws_iam_policy_document.data_engineer.json
}

# finance_analyst: read-only on the finance curated bucket, nothing else.
data "aws_iam_policy_document" "finance_analyst" {
  statement {
    actions   = ["s3:ListBucket"]
    resources = [local.finance_curated_arn]
  }

  statement {
    actions   = ["s3:GetObject"]
    resources = ["${local.finance_curated_arn}/*"]
  }
}

resource "aws_iam_role" "finance_analyst" {
  name               = "finance_analyst"
  assume_role_policy = data.aws_iam_policy_document.trust.json
}

resource "aws_iam_role_policy" "finance_analyst" {
  name   = "s3-read-finance-curated"
  role   = aws_iam_role.finance_analyst.id
  policy = data.aws_iam_policy_document.finance_analyst.json
}
