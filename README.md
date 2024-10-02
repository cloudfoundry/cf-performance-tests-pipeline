# CF Performance Tests Pipeline

This repository defines a Concourse pipeline that automatically runs the [cf-performance-tests](https://github.com/cloudfoundry/cf-performance-tests) against new releases of [cf-deployment](https://github.com/cloudfoundry/cf-deployment) and stores the [results](results) in this repo. The pipeline also generates .png charts that show how performance varies across different cf-deployment releases. These are regenerated each time a new results file is added, along with a [coverage table](results/coverage.md) that gives an overview of releases that have been tested.

The pipeline is triggered by new cf-deployment releases. It uses [bbl](https://github.com/cloudfoundry/bosh-bootloader) to stand a bosh director, and then uses that director to deploy a Cloud Foundry foundation. Each pipeline run will run the tests twice against a specific release of cf-deployment - once with a Cloud Controller that has a postgres CCDB, and once with a mysql CCDB. After completion, the bbl test environment is torn down.

See the [docs](docs) subdirectory for instructions on one-off manual setup steps that need to be run before running any tests, along with guidance on configuring new automated tests and manual setup steps for triggering a series of tests against old releases of cf-deployment.

## Test results and charts

Results are stored automatically in the following paths in this repo, according to the Cloud Controller that was tested (the go proof-of-concept or the regular CC written in rails) and whether a postgres or mysql CCDB was used.

```bash
results
├── go #tests that swap in a proof-of-concept Cloud Controller written in go: https://github.com/cloudfoundry/go-cf-api (archived results only)
│   ├── mysql
│   │   ├── charts
│   │   └── results
│   └── postgres
│       ├── charts
│       └── results
└── rails #tests using the regular Cloud Controller
    ├── mysql
    │   ├── charts
    │   └── results
    └── postgres
        ├── charts
        └── results
```

Four types of chart are generated:

1. Detailed: contains the largest, shortest and average cf api execution time.
2. Detailed with most recent runs. Same as 1, but only contains the last 15 runs.
3. Simplified: Chart only contains the average cf api execution time.
4. Simplified with most recent runs: same as 3, only contains the last 15 runs.

## General information
The AWS account and domain used to host the BBL and CF foundation is controlled by SAP, but may move to a community owned account in the future. See [here](docs/manual-setup.md) for information on the manual steps that were followed to get the tests automated.

The pipelines are running on [concourse.app-runtime-interfaces.ci.cloudfoundry.org](https://concourse.app-runtime-interfaces.ci.cloudfoundry.org/). All secrets referenced by the pipelines (e.g. `((aws-pipeline-user-secret))`) are stored in a CredHub server deployed alongside Concourse. Contributors who need access must contact the [App Runtime Interfaces Working Group](https://github.com/cloudfoundry/community/blob/main/toc/working-groups/app-runtime-interfaces.md) in order to get approval to be added to the working group's Google Cloud account. Once access is granted, you can login to CredHub with [this script](https://github.com/cloudfoundry/concourse-infra-for-fiwg/blob/45e6b798017cde94518362baa3f7441f1b029767/start-credhub-cli.sh).

### Access a performance test environment
Although the test environments are torn down automatically at the end of a successful run, you might need to access one to debug a failure.

1. Follow [these instructions](https://github.com/cloudfoundry/bosh-bootloader#prerequisites) to install `bbl` locally.
1. Navigate to the s3 bucket `cf-performance-tests` and find the subfolder for the test environment you want to connect to and download the tarball `bbl-state.tgz`.
1. Extract the archive locally, and `cd` into the `state` directory.
1. Run `eval "$(bbl print-env)"`
1. Confirm you can now communicate with the bosh director by running `bosh env`
1. You should also now be able to access the director's CredHub with the `credhub` CLI.

### Connect to the CCDB: MySQL
If you have deployed a test environment with MySQL as the Cloud Controller's database, you can open a tunnel to the jumpbox and then connect from there. Initialise `bbl` as explained above and then run:
```bash
ssh -4 -N -o "UserKnownHostsFile=/dev/null" -o "StrictHostKeyChecking=no" -o "ServerAliveInterval=30" -o "ServerAliveCountMax=10" -o "IPQoS=throughput" \
  -i "$JUMPBOX_PRIVATE_KEY" -L "3306:10.0.16.5:3306" jumpbox@<jumpbox ip from $BOSH_ALL_PROXY> &
# copy mysql client from "database" vm
bosh -d cf scp database:/usr/local/bin/mysql .
./mysql --host=127.0.0.1 --port=3306 --user=cloud_controller cloud_controller --password=<cc_database_password from credhub>
```
From the mysql command prompt, you can e.g. use `source db.sql` to read and execute statements from a file.

### Connect to the CCDB: PostgreSQL
If you have deployed a test environment with PostgreSQL as the Cloud Controller's database, you can open a tunnel to the jumpbox and then connect from there. Initialise `bbl` as explained above and then run:
```bash
ssh -4 -N -o "UserKnownHostsFile=/dev/null" -o "StrictHostKeyChecking=no" -o "ServerAliveInterval=30" -o "ServerAliveCountMax=10" -o "IPQoS=throughput" \
  -i "$JUMPBOX_PRIVATE_KEY" -L "5524:10.0.16.5:5524" jumpbox@<jumpbox ip from $BOSH_ALL_PROXY> &
```
To get PostgreSQL run:
```bash
apt-get update
apt-get install postgresql
```
To connect to psql run:
```bash
psql --host=127.0.0.1 --port=5524 --user=cloud_controller cloud_controller 
```
## Troubleshooting

The tests are fully automated, but some of the following techniques might help if you need to debug a failure:

### A pipeline task fails

1. Login to Concourse on the commandline with `fly --target bosh-cf login --concourse-url https://bosh.ci.cloudfoundry.org/`
1. In your web browser, navigate to the latest failed build (only the container for the latest build is preserved), and copy the URL.
1. In your terminal, run `fly --target bosh-cf hijack --url <BUILD_URL>`. You should connect to the container.

If the step that failed was a [task](https://concourse-ci.org/tasks.html), a consider re-running its script from the container with `-x` to log out all commands that are run. For example, if the `deploy-cf` task fails, get the name of its yaml configuration file from the pipeline file (`cf-deployment-concourse-tasks/bosh-deploy/task.yml`), and look at for the path to the script. In this case, you'll need to run `bash -x cf-deployment-concourse-tasks/bosh-deploy/task.sh`

### `bbl-up` or `bbl-destroy` fail

You can retrieve the debug logs of `bbl`, which include `terraform` logs and `bosh` CLI output, by [hijacking the appropriate task container](#a-pipeline-task-fails). The directory that your session starts in should contain a number of log files - `bbl_plan.log`, `bbl_up.log` or `bbl_destroy.txt` depending on the task.

If you're not sure whether the director actually exists, as a sanity check you might consider navigating to the AWS console and checking in eu-central-1 to see if a VM named `bosh/0` with the appropriate tags for the test environment exists and is in a `started` state.

### `deploy-cf` or `bosh-delete-deployments` fail

1. Access the director by following [these instructions](#access-a-performance-test-environment)
1. When debugging a failure it's often useful to run `bosh tasks --recent=<NUMBER>` to find the number of a failed task, and then retrieve its debug logs with `bosh task <TASK_NUMBER> --debug`.
1. Also consider setting `BOSH_LOG_LEVEL=debug` when running other commands.

### Automated teardown fails

Aside from the several dozen bosh-managed VMs created as part of a cf deployment, the pipeline creates a total of about 100 AWS resources per test in environment. Although the pipeline is written to destroy these resources upon successfully completing the tests, it also has a series of jobs that can be manually triggered to separately delete the cf bosh deployment, the bosh director, the base infrastructure (upon which the former both depend) - or all three reverse-order. These are defined in a pipeline group that you can view by clicking the `manual-teardown` button in the top-left of the Concourse UI when viewing the pipeline in question.

> Warning: If you run `manual-teardown-base-infra-only` deletes the IAM user and associated policy that `bbl` depends on to manage resources in AWS. You should not run this before `bbl` has destroyed those resources.

If these manual jobs fail to clean up an environment, you will need to locate the test environment's subfolder in the `cf-performance-tests` S3 bucket and, depending on the failure, download either `bbl-state.tgz` or `base-infra/terraform.tfstate`.
- `bbl-state.tgz`:
    1. Extract the archive and change into the state directory
    1. Run `eval "$(bbl print-env)"` and then `bosh vms` to check if any bosh-managed vms still exist. If they do, try to delete them with bosh (if this fails, you'll have to do this manually in AWS)
    1. If there are no bosh-managed VMs left but you've still got a director, try to delete it with `bbl destroy`. If this fails, you'll have to delete the director and jumpbox VMs manually in AWS.
    1. If `bbl destroy` is unable to delete the director, or succeeds but then fails while destroying terraform resources, you'll have to try to delete these yourself.
    1. Download version 0.11.x of the `terraform` CLI, and move `vars/terraform.tfstate` and `vars/bbl.tfvars` into the `terraform` subdirectory.
    1. Run `terraform init` and provide the values for any required variables, then `terraform destroy -var-file=bbl.tfvars`. You may need to remove resources from the tls provider from the state file.
- `base-infra/terraform.tfstate`
    1. Download the file, place it in [base-infra/terraform](../base-infra/terraform), and run `terraform init` with whatever version of the terraform CLI matches that used by the latest commit of the [Concourse terraform resource](https://github.com/ljfranklin/terraform-resource) when the pipeline last ran the `base-infra` job. Then `terraform destroy`.

In both cases, the last resort - and this should almost never be necessary - will be to manually delete any remaining resources from AWS
