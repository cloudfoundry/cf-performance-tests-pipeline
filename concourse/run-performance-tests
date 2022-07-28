#!/bin/bash

set -eu

echo -e "\nGetting test landscape configuration from bbl state..."
pushd "bbl-state/state" > /dev/null
  eval "$(bbl print-env)"
  BOSH_DIRECTOR_NAME="$(<bbl-state.json jq -r .bosh.directorName)"
  CF_ADMIN_PASSWORD="$(credhub get -n "/$BOSH_DIRECTOR_NAME/cf/cf_admin_password" -j | jq -r .value)"
  CF_DOMAIN="$(<bbl-state.json jq -r .lb.domain)"
  JUMPBOX_URL="$(<./vars/jumpbox-vars-file.yml yq -r .external_ip)"
  JUMPBOX_PRIVATE_KEY="$(<./vars/jumpbox-vars-store.yml yq -r .jumpbox_ssh.private_key)"
  DATABASE_IP="$(bosh -d cf vms --json | jq -r '.Tables[0].Rows[] | select(.instance | startswith("database/")) | .ips')"
  CCDB_PASSWORD="$(credhub get -n "/$BOSH_DIRECTOR_NAME/cf/cc_database_password" -j | jq -r .value)"
  UAADB_PASSWORD="$(credhub get -n "/$BOSH_DIRECTOR_NAME/cf/uaa_database_password" -j | jq -r .value)"
popd > /dev/null

echo -e "\nGetting cf-deployment version..."
# TODO if possible we could also get the cloud_controller_ng commit
CF_DEPLOYMENT_VERSION="$(<./cf-deployment/cf-deployment.yml yq '.manifest_version' -r)"
CAPI_VERSION="$(<./cf-deployment/cf-deployment.yml grep -A 1 capi | grep version | cut -d ':' -f2 | sed 's/ //g')"

echo -e "\nLogging in to CF and creating a test user..."
cf api --skip-ssl-validation "api.$CF_DOMAIN"
cf auth admin "$CF_ADMIN_PASSWORD"
cf create-user perf-test-user perf-test-password

if [ -z "${DATABASE_TYPE:-}" ]; then
  echo "Task parameter 'DATABASE_TYPE' is empty. Falling back to 'postgres'."
  DATABASE_TYPE="postgres"
fi
if [ "${DATABASE_TYPE}" == 'postgres' ]; then
  DATABASE_PORT=5524
  DATABASE_CCDB="postgres://cloud_controller:$CCDB_PASSWORD@localhost:$DATABASE_PORT/cloud_controller?sslmode=disable"
  DATABASE_UAADB="postgres://uaa:$UAADB_PASSWORD@localhost:$DATABASE_PORT/uaa?sslmode=disable"
elif [ "${DATABASE_TYPE}" == 'mysql' ]; then
  DATABASE_PORT=3306
  DATABASE_CCDB="cloud_controller:$CCDB_PASSWORD@tcp(localhost:$DATABASE_PORT)/cloud_controller?multiStatements=true"
  DATABASE_UAADB="uaa:$UAADB_PASSWORD@tcp(localhost:$DATABASE_PORT)/uaa?multiStatements=true"
else
  echo "Task parameter 'DATABASE_TYPE' must be one of 'postgres' or 'mysql' (is: ${DATABASE_TYPE})."
  exit 1
fi

echo -e "\nOpening SSH tunnel to CF database..."
echo "$JUMPBOX_PRIVATE_KEY" > ./jumpbox_private.key
chmod 0600 ./jumpbox_private.key
ssh -4 -N -o "UserKnownHostsFile=/dev/null" -o "StrictHostKeyChecking=no" -o "ServerAliveInterval=30" -o "ServerAliveCountMax=10" -o "IPQoS=throughput" -i ./jumpbox_private.key -L "$DATABASE_PORT":"$DATABASE_IP":"$DATABASE_PORT" jumpbox@"$JUMPBOX_URL" &
SSH_PID=$!

echo -e "\nRunning cf-performance tests..."
if [ -z "${TEST_RESULTS_FOLDER:-}" ]; then
  echo "Task parameter 'TEST_RESULTS_FOLDER' is empty. Check pipeline configuration."
  exit 1
fi
TEST_RESULTS="$PWD/$TEST_RESULTS_FOLDER"
pushd "./cf-performance-tests" > /dev/null
  cat << EOF > ./config.yml
api: "api.$CF_DOMAIN"
skip_ssl_validation: true
cf_deployment_version: "$CF_DEPLOYMENT_VERSION"
capi_version: "$CAPI_VERSION"
users:
  admin:
    username: "admin"
    password: "$CF_ADMIN_PASSWORD"
database_type: "$DATABASE_TYPE"
ccdb_connection: "$DATABASE_CCDB"
uaadb_connection: "$DATABASE_UAADB"
samples: 10
results_folder: "$TEST_RESULTS"
EOF
  if [ -z "${TEST_SUITE_FOLDER:-}" ]; then
    ginkgo ./...
  else
    ginkgo -r "$TEST_SUITE_FOLDER"
  fi
popd > /dev/null

echo -e "\nPushing cf-performance test results..."
# must copy original git repository to the "repository" folder specified in the "put" resource
cp -r "perf-test-repo/." "performance-test-results/"

echo -e "\n Installing git lfs"
tmpdir="$(mktemp -d git_lfs_install.XXXXXX)"

cd "$tmpdir"
curl -Lo git.tar.gz https://github.com/github/git-lfs/releases/download/v1.1.0/git-lfs-linux-386-1.1.0.tar.gz
gunzip git.tar.gz
tar xf git.tar
mv git-lfs-1.1.0/git-lfs /usr/bin
cd ..
rm -rf "$tmpdir"
git lfs install

pushd "performance-test-results" > /dev/null
  status="$(git status --porcelain)"
  if [[ -n "$status" ]]; then
    git config user.name "${GIT_COMMIT_USERNAME}"
    git config user.email "${GIT_COMMIT_EMAIL}"
    git add --all .
    git commit -m "${GIT_COMMIT_MESSAGE}"
  fi
popd > /dev/null

echo "Killing background ssh tunnel..."
kill $SSH_PID

echo "Finished."
