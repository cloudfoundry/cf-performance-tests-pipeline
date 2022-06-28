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

There are two Concourse pipelines for the automatic deployment and destruction of a CF foundation. Log on to Concourse with the "fly" CLI and upload the pipelines. The "cf-perf-test" variables configure the pipelines for the default CF deployment. The "go-perf-test" variables are for the CF deployment with the new go-cf-api reimplementation.

**NOTE**: The credentials which are referenced in the pipeline yaml are stored in Concourse Credhub (and SAP internal).

### CF Performance Tests Pipeline

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

**Note:** The following variable references in `variables/vars-go-perf-common.yml` need to be replaced:
- `cf-perf-aws-access-key-secret` with `go-perf-aws-access-key-secret`
- `cf-perf-aws-access-key-id` with `go-perf-aws-access-key-id`
- `cf-perf-bbl-state-bucket-access-key-id` with `go-perf-bbl-state-bucket-access-key-id`
- `cf-perf-bbl-state-bucket-access-key-secret` with `go-perf-bbl-state-bucket-access-key-secret`

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


The deploy pipeline runs `bbl up` followed by a `bosh deploy` for the CF deployment. Then it executes the performance tests and generates visual charts. Test results and charts are automatically uploaded to github. The pipeline also runs the CF Acceptance Tests and finally destroys the "cf" BOSH deployment to save cost.

The destroy pipeline first deletes all BOSH deployments and then runs `bbl destroy` to delete all IaaS resources. Use this only if you want to tear down the complete environment.


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