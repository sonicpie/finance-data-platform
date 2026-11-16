# One domain's two buckets, each with encryption and a lifecycle policy.

variable "domain" {
  description = "Domain name, used as the bucket name prefix (finance -> finance-data-landing)."
  type        = string
}

resource "aws_s3_bucket" "this" {
  for_each = toset(["landing", "curated"])

  bucket = "${var.domain}-data-${each.key}"
}

# SSE-S3: S3 encrypts every object with a key that AWS manages.
resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Move objects to cheaper storage as they age. Nothing is ever deleted.
resource "aws_s3_bucket_lifecycle_configuration" "this" {
  for_each = aws_s3_bucket.this

  bucket = each.value.id

  rule {
    id     = "move-to-cheaper-storage"
    status = "Enabled"

    filter {} # empty filter = every object in the bucket

    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
  }
}

output "bucket_arns" {
  description = "Bucket ARNs, e.g. { landing = \"arn:aws:s3:::finance-data-landing\", curated = ... }"
  value       = { for zone, bucket in aws_s3_bucket.this : zone => bucket.arn }
}
