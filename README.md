# CF Performance Tests Pipeline

This repository contains all artifacts for the CF performance tests pipeline including bootstrapping of the CF foundation, which tests run against and the [test results](test-results) and generated [charts](test-charts). It is based on [bosh-bootloader](https://github.com/cloudfoundry/bosh-bootloader) and [cf-deployment](https://github.com/cloudfoundry/cf-deployment). The deployment pipeline runs on this public Concourse instance: https://bosh.ci.cloudfoundry.org/. You can log on with your github.com account.

The performance tests can be found [here](https://github.com/cloudfoundry/cf-performance-tests)

## Test Results / Test Charts

After finishing running the concourse pipeline, all results and charts are saved in the corresponding directories in this repo. You can visually observe the regressions/improvements of performance from the charts.

[domains-test-results](test-results/domains-test-results/v1/) / [domains-test-charts](test-charts/domains-test-results/v1/)

[security-groups-test-results](test-results/security-groups-test-results/v1) / [security-groups-test-charts](test-charts/security-groups-test-results/v1/)

[isolation-segments-test-results](test-results/isolation-segments-test-results/v1/) / [isolation-segments-test-charts](test-charts/isolation-segments-test-results/v1/)

[service-keys-test-results](test-results/service-keys-test-results/v1/) / [service-keys-test-charts](test-charts/service-keys-test-results/v1/)

Several types of chart data will be generated:

1. Detailed: contains the largest, shortest and average cf api execution time.
2. Detailed with most recent runs. Same as 1, but only contains the last 15 runs.
3. Simplified: Chart only contains the average cf api execution time.
4. Simplified with most recent runs: same as 3, only contains the last 15 runs.

## General information
The AWS account and domain used to host the BBL and CF foundation is currently owned by SAP. It might move to a community owned account in the future. A description of how this was set up can be found [here](docs/manual-setup.md).

## Automatic Setup / Destruction

There are three Concourse pipelines for the automatic deployment and destruction of a CF foundation. Log on to Concourse with the "fly" CLI and upload the pipelines. The "deploy-cf-performance-test" pipeline deploys and tests a default CF deployment. "deploy-cf-mysql-performance-test" uses MySQL as cloud controller database instead of PostgreSQL. The "deploy-go-performance-test" pipeline deploys CF with the new go-cf-api reimplementation.

**NOTE**: The credentials which are referenced in the pipeline yaml are stored in Concourse CredHub (and SAP internal).

## CF Performance Tests Pipelines

The deploy pipelines run `bbl up` followed by a `bosh deploy` for the CF deployment. Then they execute the performance tests and generate visual charts. Test results and charts are automatically uploaded to github. The pipelines also run the CF Acceptance Tests and finally destroy the "cf" BOSH deployment to save cost.

The destroy pipelines first delete all BOSH deployments and then run `bbl destroy` to delete all IaaS resources. Use this only if you want to tear down the complete environment.

### CF Performance Tests Pipeline

Store the following credentials in the Concourse CredHub:
```
/concourse/cf-controlplane/cf-perf-aws-access-key-secret
/concourse/cf-controlplane/cf-perf-aws-access-key-id
/concourse/cf-controlplane/cf-perf-bbl-state-bucket-access-key-secret
/concourse/cf-controlplane/cf-perf-bbl-state-bucket-access-key-id
```

#### Deploy-Pipeline
```bash
fly -t <target> set-pipeline -p deploy-cf-performance-test
  --load-vars-from=variables/vars-cf-perf-common.yml \
  -c ./concourse/deploy-cf-perftest.yml
```
#### Destroy-Pipeline
```bash
fly -t <target> set-pipeline -p destroy-cf-performance-test
  --load-vars-from=variables/vars-cf-perf-common.yml \
  -c ./concourse/destroy-cf-perftest.yml
```

### Go Performance Tests Pipeline

Store these credentials in the Concourse CredHub:
```
/concourse/cf-controlplane/go-perf-aws-access-key-secret
/concourse/cf-controlplane/go-perf-aws-access-key-id
/concourse/cf-controlplane/go-perf-bbl-state-bucket-access-key-id
/concourse/cf-controlplane/go-perf-bbl-state-bucket-access-key-secret
```

#### Deploy-Pipeline
```bash
fly -t <target> set-pipeline -p deploy-go-performance-test
  --load-vars-from=variables/vars-go-perf-common.yml \
  -c ./concourse/deploy-cf-perftest.yml
```

#### Destroy-Pipeline
```bash
fly -t <target> set-pipeline -p destroy-go-performance-test
  --load-vars-from=variables/vars-cf-perf-common.yml \
  -c ./concourse/destroy-cf-perftest.yml
```

### MySQL Performance Tests Pipeline

Store these credentials in the Concourse CredHub:
```
/concourse/cf-controlplane/cf-mysql-perf-bbl-state-bucket-access-key-id
/concourse/cf-controlplane/cf-mysql-perf-bbl-state-bucket-access-key-secret
/concourse/cf-controlplane/cf-mysql-perf-aws-access-key-id
/concourse/cf-controlplane/cf-mysql-perf-aws-access-key-secret
```

#### Deploy-Pipeline
```bash
fly -t <target> set-pipeline -p deploy-cf-mysql-performance-test
  --load-vars-from=variables/vars-cf-mysql-perf-common.yml \
  -c ./concourse/deploy-cf-perftest.yml
```

#### Destroy-Pipeline
```bash
fly -t <target> set-pipeline -p destroy-cf-mysql-performance-test
  --load-vars-from=variables/vars-cf-mysql-perf-common.yml \
  -c ./concourse/destroy-cf-perftest.yml
```

## Troubleshooting
### Login to Concourse with `fly`
```bash
fly login  -t bosh-cf  -c https://bosh.ci.cloudfoundry.org/ -n cf-controlplane
```

### Access performance test landscape
Follow those steps to access the performance test landscape. The landscape is deployed with [bbl](https://github.com/cloudfoundry/bosh-bootloader) 
- Download state from IaaS account (s3)
- Unpack state
- Copy `state` into this repo
- Setup bbl with `eval "$(bbl print-env)"`
- `bosh deployments` etc. should work now

### Connect to Concourse Credhub
Run [this script](https://github.com/cloudfoundry/bosh-community-stemcell-ci-infra/blob/main/start-credhub-cli.sh), it requires access to the Bosh-CI Concourse GCP project.

### Connect to MySQL Database
If you have deployed CF with MySQL as cloud controller database, you can open a tunnel to the jumpbox and then connect to the database. Initialise bbl as explained above and then run:
```bash
ssh -4 -N -o "UserKnownHostsFile=/dev/null" -o "StrictHostKeyChecking=no" -o "ServerAliveInterval=30" -o "ServerAliveCountMax=10" -o "IPQoS=throughput" \
  -i "$JUMPBOX_PRIVATE_KEY" -L "3306:10.0.16.5:3306" jumpbox@<jumpbox ip from $BOSH_ALL_PROXY> &
# copy mysql client from "database" vm
bosh -d cf scp database:/usr/local/bin/mysql .
./mysql --host=127.0.0.1 --port=3306 --user=cloud_controller cloud_controller --password=<cc_database_password from credhub>
```
From the mysql command prompt, you can e.g. use `source db.sql` to read and execute statements from a file.
