#!/bin/bash

set -euo pipefail

task_root="$(pwd)"
cf_perf_tests_pipeline_repo="${task_root}/cf-performance-tests-pipeline"
cf_perf_tests_repo="${task_root}/cf-performance-tests"
results_path="/tmp/results/${CLOUD_CONTROLLER_TYPE}/${CCDB}/results"
cf_deployment_repo="${task_root}/cf-deployment"
bbl_state="${task_root}/bbl-state/${BBL_STATE_DIR}"

mkdir -p "$results_path"

echo -e "\nGetting test landscape configuration from bbl state..."
pushd "$bbl_state" >/dev/null
  eval "$(bbl print-env)"
  bosh_director_name="$(<bbl-state.json jq --raw-output '.bosh.directorName')"
  cf_admin_password="$(credhub get --name "/${bosh_director_name}/cf/cf_admin_password" --output-json | jq --raw-output '.value')"
  cf_domain="$(<bbl-state.json jq --raw-output '.lb.domain')"
  jumpbox_url="$(<./vars/jumpbox-vars-file.yml yq --raw-output '.external_ip')"
  jumpbox_private_key="$(<./vars/jumpbox-vars-store.yml yq --raw-output '.jumpbox_ssh.private_key')"
  database_ip="$(bosh -d cf vms --json | jq --raw-output '.Tables[0].Rows[] | select(.instance | startswith("database/")) | .ips')"
  ccdb_password="$(credhub get --name "/${bosh_director_name}/cf/cc_database_password" --output-json | jq --raw-output '.value')"
  uaadb_password="$(credhub get --name "/${bosh_director_name}/cf/uaa_database_password" --output-json | jq --raw-output '.value')"
popd >/dev/null

echo -e "\nGetting cf-deployment version..."
cf_deployment_version="$(<"${cf_deployment_repo}"/cf-deployment.yml yq '.manifest_version' -r)"
capi_version="$(<"${cf_deployment_repo}"/cf-deployment.yml grep -A 1 capi | grep version | cut -d ':' -f2 | sed 's/ //g')"

echo -e "\nLogging in to CF and creating a test user..."
cf api --skip-ssl-validation "api.${cf_domain}"
cf auth admin "$cf_admin_password"

if [ "$CCDB" == 'postgres' ]; then
  database_port=5524
  database_ccdb="postgres://cloud_controller:${ccdb_password}@${database_ip}:${database_port}/cloud_controller?sslmode=disable"
  database_uaadb="postgres://uaa:${uaadb_password}@${database_ip}:${database_port}/uaa?sslmode=disable"
elif [ "$CCDB" == 'mysql' ]; then
  database_port=3306
  database_ccdb="cloud_controller:${ccdb_password}@tcp(${database_ip}:${database_port})/cloud_controller?multiStatements=true"
  database_uaadb="uaa:${uaadb_password}@tcp(${database_ip}:${database_port})/uaa?multiStatements=true"
else
  echo "Task parameter 'CCDB' must be one of 'postgres' or 'mysql' (is: ${CCDB})."
  exit 1
fi

pushd "$cf_perf_tests_repo" >/dev/null
  cat << EOF > ./config.yml
api: "localhost:9024"
use_http: false
skip_ssl_validation: true
cf_deployment_version: "$cf_deployment_version"
capi_version: "$capi_version"
users:
  admin:
    username: "admin"
    password: "$cf_admin_password"
database_type: "$CCDB"
ccdb_connection: "$database_ccdb"
uaadb_connection: "$database_uaadb"
samples: 30
results_folder: "$results_path"
EOF
popd >/dev/null

# Cleanup/Prepare
rm -rf cf-performance-tests.tar.gz
bosh -d cf ssh -c 'sudo rm -rf /tmp/* && sudo mount -o remount,exec /tmp' api/0

# Copy Tests to VM and execute them
pushd ${task_root}
  tar -czvf cf-performance-tests.tar.gz cf-performance-tests
  bosh -d cf scp "${PWD}/cf-performance-tests.tar.gz" api/0:/tmp/
popd
bosh -d cf scp "${cf_perf_tests_pipeline_repo}/ci/tasks/run-performance-tests/task_on_vm.sh" api/0:/tmp/
bosh -d cf ssh -c "cd /tmp/ && TEST_SUITE_FOLDER=${TEST_SUITE_FOLDER} GINKGO_TIMEOUT=${GINKGO_TIMEOUT} ./task_on_vm.sh" api/0

# Copy back results and extract them
bosh -d cf scp api/0:/tmp/results.tar.gz "${cf_perf_tests_pipeline_repo}/results.tar.gz"
pushd "$cf_perf_tests_pipeline_repo" >/dev/null
  tar -xzvf results.tar.gz
  rm -rf results.tar.gz
popd >/dev/null

echo -e "\n Installing git lfs"
apt-get update && apt-get -y install git-lfs
git lfs install

if [[ $(git -C "$cf_perf_tests_pipeline_repo" status --porcelain) ]]; then
  echo -e "\nCommitting test results..."
  git -C "$cf_perf_tests_pipeline_repo" config user.name "$GIT_COMMIT_USERNAME"
  git -C "$cf_perf_tests_pipeline_repo" config user.email "$GIT_COMMIT_EMAIL"
  git -C "$cf_perf_tests_pipeline_repo" add --all "$cf_perf_tests_pipeline_repo/results"
  git -C "$cf_perf_tests_pipeline_repo" commit -m "$GIT_COMMIT_MESSAGE"
fi

echo -e "\nFinished."
