#! /bin/bash

set -e

export AWS_PAGER="" 
: "${AWS_DEFAULT_REGION:=eu-central-1}"

script_dir="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
cloudformation_template="file://${script_dir}/bootstrap.yml"
stack_name=cf-performance-tests-shared

if aws cloudformation describe-stacks --stack-name "$stack_name" >/dev/null 2>/dev/null; then
  echo "Updating stack..."
  aws cloudformation update-stack --stack-name "$stack_name" --capabilities CAPABILITY_NAMED_IAM --template-body "$cloudformation_template"
else
  echo "Creating stack..."
  aws cloudformation create-stack --stack-name "$stack_name" --capabilities CAPABILITY_NAMED_IAM --template-body "$cloudformation_template" --on-failure DO_NOTHING
  aws cloudformation wait stack-create-complete --stack-name "$stack_name"
fi

aws cloudformation list-stack-resources --stack-name "$stack_name" --output yaml
creds_arn="$(aws cloudformation describe-stacks --stack-name "$stack_name" --query "Stacks[0].Outputs[?OutputKey=='PipelineUserCredsARN'].OutputValue" --output text)"
echo -e "\n$(tput setaf 0)$(tput bold)Ensure that the AWS credentials of the created user (found at $(tput setaf 4)${creds_arn}$(tput setaf 0)$(tput bold)) are added to credhub under /concourse/cf-controlplane/aws-pipeline-user-id and /concourse/cf-controlplane/aws-pipeline-user-secret"