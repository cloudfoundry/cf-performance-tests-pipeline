#!/bin/bash

set -euo pipefail

task_root="$(pwd)"
cf_deployment_repo="${task_root}/cf-deployment"
next_version_repo="${task_root}/next-version"
capi_release_repo="${task_root}/capi-release-ci-passed"
cf_versions_output="${task_root}/cf-versions"

echo -e "\nGetting cf-deployment and capi versions..."
cf_deployment_version="$(yq '.manifest_version' -r "${cf_deployment_repo}/cf-deployment.yml")"
capi_release_short_ref="$(tr -d '[:space:]' < "${capi_release_repo}/.git/short_ref")"
capi_version="$(tr -d '[:space:]' < "${next_version_repo}/version") (${capi_release_short_ref})"

echo "cf_deployment_version: ${cf_deployment_version}" >> "${cf_versions_output}/cf_versions.yml"
echo "capi_version: ${capi_version}" >> "${cf_versions_output}/cf_versions.yml"

cat "${cf_versions_output}/cf_versions.yml"
