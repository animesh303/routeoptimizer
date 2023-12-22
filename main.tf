provider "aws" {
  region = "us-east-1" # Set your desired AWS region
}

# resource "null_resource" "zip_lambda_src" {
#   provisioner "local-exec" {
#     command     = "zip -r RouteOptimizer.zip RouteOptimizer.py"
#     working_dir = "${path.module}/src/functions"
#   }

# }

# Data source to create a ZIP archive
data "archive_file" "RouteOptimizerSrc" {
  type        = "zip"
  source_dir  = "${path.module}/src/functions"
  output_path = "${path.module}/artifacts/RouteOptimizer.zip"

  #   source {
  #     content  = data.template_file.vimrc.rendered
  #     filename = "${path.module}/src/functions/RouteOptimizer.py"
  #   }

}

# data "local_file" "lambda_layer_zip" {
#   filename = "${path.module}/src/layers/panda_layer.zip"
# }

variable "google_api_key" {
  description = "Google API key Secret"
}

variable "lunch_duration_mins" {
  description = "Lunch duration in minutes"
}

variable "dinner_duration_mins" {
  description = "Dinner duration in minutes"
}

variable "lunch_hr" {
  description = "Lunch starting hour"
}

variable "dinner_hr" {
  description = "Dinner starting hour"
}

resource "aws_lambda_layer_version" "pandas_layer" {
  layer_name          = "pandas"
  description         = "Pandas Libraries"
  compatible_runtimes = ["python3.10"] # Set the compatible runtime for your layer

  #   filename         = data.local_file.lambda_layer_zip.output_path
  #   source_code_hash = data.local_file.lambda_layer_zip.output_base64sha256

  source_code_hash = filebase64sha256("${path.module}/src/layers/panda_layer.zip")
  filename         = "${path.module}/src/layers/panda_layer.zip"

}

resource "aws_lambda_function" "RouteOptimizer" {
  function_name = "RouteOptimizer"
  handler       = "RouteOptimizer.lambda_handler"
  runtime       = "python3.10"

  role = aws_iam_role.RouteOptimizerFnRole.arn # Reference to the IAM role ARN that grants permissions to the Lambda function

  # Specify the location of your Python script
  #   filename         = "${path.module}/src/functions/RouteOptimizer.zip"
  #   source_code_hash = filebase64("${path.module}/src/functions/RouteOptimizer.zip")

  filename         = data.archive_file.RouteOptimizerSrc.output_path
  source_code_hash = data.archive_file.RouteOptimizerSrc.output_base64sha256

  layers = [aws_lambda_layer_version.pandas_layer.arn]
  environment {
    variables = {
      assignment_bucket    = aws_s3_bucket.attractions_source.bucket
      google_api_key       = aws_ssm_parameter.google_api_key.name
      lunch_duration_mins  = var.lunch_duration_mins
      dinner_duration_mins = var.dinner_duration_mins
      lunch_hr             = var.lunch_hr
      dinner_hr            = var.dinner_hr
    }
  }

  timeout = 600

  depends_on = [
    aws_iam_role_policy_attachment.routeoptimizer_logspolicyattachment,
    # aws_cloudwatch_log_group.routeoptimizer,
  ]

}

# resource "aws_cloudwatch_log_group" "routeoptimizer" {
#   name              = "/aws/lambda/routeoptimizer"
#   retention_in_days = 14
# }

resource "aws_iam_role_policy_attachment" "routeoptimizer_logspolicyattachment" {
  role       = aws_iam_role.RouteOptimizerFnRole.name
  policy_arn = aws_iam_policy.lambda_logging.arn
}

resource "aws_iam_policy" "lambda_logging" {
  name        = "lambda_logging"
  path        = "/"
  description = "IAM policy for logging from a lambda"
  policy      = data.aws_iam_policy_document.lambda_logging.json
}

data "aws_iam_policy_document" "lambda_logging" {
  statement {
    effect = "Allow"

    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = ["arn:aws:logs:*:*:*"]
  }
}



resource "aws_iam_role" "RouteOptimizerFnRole" {
  name = "RouteOptimizerFnRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Action = "sts:AssumeRole",
      Effect = "Allow",
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_policy" "s3_access_policy" {
  name        = "s3-access-policy"
  description = "Policy to grant S3 bucket access"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:PutObjectAcl",
        ],
        Effect = "Allow",
        Resource = [
          aws_s3_bucket.attractions_source.arn,
          "${aws_s3_bucket.attractions_source.arn}/*",
        ],
      },
    ],
  })
}

resource "aws_iam_policy_attachment" "s3_access_policy_attachment" {
  name       = "s3-access-policy"
  policy_arn = aws_iam_policy.s3_access_policy.arn
  roles      = [aws_iam_role.RouteOptimizerFnRole.name]
}


resource "aws_iam_policy" "secrets_access_policy" {
  name        = "secrets-access-policy"
  description = "Policy to grant Secrets"

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "ssm:GetParameter"
        ],
        Effect = "Allow",
        Resource = [
          aws_ssm_parameter.google_api_key.arn
        ],
      },
    ],
  })
}

resource "aws_iam_policy_attachment" "secrets_access_policy_attachment" {
  name       = "secrets-access-policy"
  policy_arn = aws_iam_policy.secrets_access_policy.arn
  roles      = [aws_iam_role.RouteOptimizerFnRole.name]
}


resource "aws_s3_bucket" "attractions_source" {
  force_destroy = true
}


resource "aws_s3_object" "attactions_file" {
  bucket = aws_s3_bucket.attractions_source.id
  key    = "attractions.xlsx"
  source = "${path.module}/data/attractions.xlsx"

  # The filemd5() function is available in Terraform 0.11.12 and later
  # For Terraform 0.11.11 and earlier, use the md5() function and the file() function:
  # etag = "${md5(file("path/to/file"))}"
  etag = filemd5("${path.module}/data/attractions.xlsx")
}


resource "aws_ssm_parameter" "google_api_key" {
  name        = "/google/api/key"
  description = "Google API key"
  type        = "SecureString"
  value       = var.google_api_key
}


resource "aws_s3_bucket_cors_configuration" "cors" {
  bucket = aws_s3_bucket.attractions_source.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "PUT", "POST", "DELETE", "HEAD"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3000
  }
}

output "assignment_bucket" {
  value = aws_s3_bucket.attractions_source.id
}

output "routeoptimizer_function" {
  value = aws_lambda_function.RouteOptimizer.arn
}