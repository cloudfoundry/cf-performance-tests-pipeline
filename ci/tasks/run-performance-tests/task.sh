#!/bin/bash

set -euo pipefail

task_root="$(pwd)"
cf_perf_tests_pipeline_repo="${task_root}/cf-performance-tests-pipeline"
cf_perf_tests_repo="${task_root}/cf-performance-tests"
results_path="${cf_perf_tests_pipeline_repo}/results/${CLOUD_CONTROLLER_TYPE}/${CCDB}/results"
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
  database_ccdb="postgres://cloud_controller:${ccdb_password}@localhost:${database_port}/cloud_controller?sslmode=disable"
  database_uaadb="postgres://uaa:${uaadb_password}@localhost:${database_port}/uaa?sslmode=disable"
elif [ "$CCDB" == 'mysql' ]; then
  database_port=3306
  database_ccdb="cloud_controller:${ccdb_password}@tcp(localhost:${database_port})/cloud_controller?multiStatements=true"
  database_uaadb="uaa:${uaadb_password}@tcp(localhost:${database_port})/uaa?multiStatements=true"
else
  echo "Task parameter 'CCDB' must be one of 'postgres' or 'mysql' (is: ${CCDB})."
  exit 1
fi

jumpbox_private_key_file="$(mktemp)"
chmod 0600 "$jumpbox_private_key_file"
cat <<EOF > "$jumpbox_private_key_file"
$jumpbox_private_key
EOF

echo -e "\nOpening SSH tunnel to CF database..."
ssh -4 -N -o "UserKnownHostsFile=/dev/null" -o "StrictHostKeyChecking=no" -o "ServerAliveInterval=30" -o "ServerAliveCountMax=10" -o "IPQoS=throughput" -i "$jumpbox_private_key_file" -L "$database_port":"$database_ip":"$database_port" jumpbox@"$jumpbox_url" &
ssh_pid=$!

pushd "$cf_perf_tests_repo" >/dev/null
  cat << EOF > ./config.yml
api: "api.${cf_domain}"
skip_ssl_validation: true
cf_deployment_version: "${cf_deployment_version}_INDICES"
capi_version: "${capi_version}_INDICES"
users:
  admin:
    username: "admin"
    password: "$cf_admin_password"
database_type: "$CCDB"
ccdb_connection: "$database_ccdb"
uaadb_connection: "$database_uaadb"
samples: 100
results_folder: "$results_path"
EOF
  if [ -z "${TEST_SUITE_FOLDER:-}" ]; then
    echo -e "\nRunning all tests..."
    go run github.com/onsi/ginkgo/v2/ginkgo run --timeout $GINKGO_TIMEOUT ./...
  else
    echo -e "\nRunning tests in ${TEST_SUITE_FOLDER}..."
    go run github.com/onsi/ginkgo/v2/ginkgo run --timeout $GINKGO_TIMEOUT -r "$TEST_SUITE_FOLDER"
  fi
popd >/dev/null

echo -e "\n Installing git lfs"
apt-get update && apt-get -y install git-lfs
git lfs install

if [[ $(git -C "$cf_perf_tests_pipeline_repo" status --porcelain) ]]; then
  echo -e "\nCommitting test results..."
  git -C "$cf_perf_tests_pipeline_repo" config user.name "$GIT_COMMIT_USERNAME"
  git -C "$cf_perf_tests_pipeline_repo" config user.email "$GIT_COMMIT_EMAIL"
  git -C "$cf_perf_tests_pipeline_repo" add --all "$results_path"
  git -C "$cf_perf_tests_pipeline_repo" commit -m "$GIT_COMMIT_MESSAGE"
fi

echo "Killing background ssh tunnel..."
kill "$ssh_pid"

echo -e "\nFinished."
