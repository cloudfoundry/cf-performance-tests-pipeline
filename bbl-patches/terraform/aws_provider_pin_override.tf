# Pin AWS provider to the last known-good version. Starting with 6.48.0 / 6.49.0,
# bbl up fails in deploy-director with:
#   "loadBalancerAttributes' failed to satisfy constraint: Member must not be null"
# from the AWS API when creating the aws_lb_target_groups defined in bbl-template.tf.
# 6.47.0 was used by the last successful run on 2026-06-03.
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 6.47.0"
    }
  }
}
