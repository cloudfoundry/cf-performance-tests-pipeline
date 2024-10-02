### Manual steps

## AWS setup

In order to automate the end-to-end deployment and destruction of the test environments, a number of AWS resources - shared between those test environments need to first be created first. Those resources are:

* An IAM user
* A policy for that IAM user
* Access keys for the user
* Storage of those keys in AWS Secrets Manager
* An S3 bucket (`cf-performance-tests`) to store the state of (all) the test environments

These resources are created by a CloudFormation stack defined in [scripts/bootstrap.yml](../scripts/bootstrap.yml) which is in turn called by the bash script [scripts/bootstrap.sh](../bootstrap.sh).

1. Install the [aws CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html) and authenticate with SAP's AWS account with a user whose permissions exceed those defined in `bootstrap.yml` for the `PipelineUser`.
1. Run `bootstrap.sh`. Upon completion the script will output the arn for the secret holding that user's AWS keys. 
1. Retrieve the access key and secret key from AWS Secrets Manager, either in your browser or with the `aws` CLI.
1. Authenticate with [Concourse's CredHub](../README.md#general-information) and store these as follows:
    ```bash
    credhub set --name /concourse/cf-controlplane/aws-pipeline-user-id --type value --value <AWS_ACCESS_KEY_ID>
    credhub set --name /concourse/cf-controlplane/aws-pipeline-user-secret --type value --value <AWS_SECRET_ACCESS_KEY>
    ```

## Configuring automatic tests
### Variables

In order to define a test configuration (e.g. with a specific ops file) that will be tested automatically against future releases of cf-deployment, define a variables file in `variables/` with the following structure:
  ```yaml
  cloud_controller_type: rails # only 'rails' supported
  additional-ops-files: " operations/use-postgres.yml" #any bosh operations files required to deploy cf. The single character of whitespace at the beginning is mandatory.
  cf_router_idle_timeout_secs: "60" #adjust as desired to change the router timeout
  test_suffix: "" #optional naming suffix for the test configuration. Must be provided as an empty string if you don't want to use it.
  ```

The name of the file must follow this format: `<cloud_controller_type><test_suffix>.yml`. If no `test_suffix` is set, simply name the file `<cloud_controller_type>.yml`.

### Set the pipeline

After being set for the first time, the first job in the pipeline will set itself thereafter when there are new commits to this repo. You will still need to set it manually in some situations, such as when a new commit adds or renames a pipeline variable.

Whatever the case case, manually set the pipeline with the following command:

```bash
fly --target bosh-cf set-pipeline \
  --pipeline <PIPELINE-NAME> \
  --load-vars-from=variables/<VARS-FILE>.yml \
  --load-vars-from variables/common.yml \
  --config ci/pipeline.yml
```

Strictly speaking you're free to choose any pipeline name you like. Just use a name that's consistent with those for other test configurations.