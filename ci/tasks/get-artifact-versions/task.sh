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

release_tag="$(git -C "${capi_release_repo}" tag --points-at HEAD | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | head -n 1 || true)"
if [[ -n "${release_tag}" ]]; then
  capi_version="${release_tag} (${capi_release_short_ref})"
else
  next_version="$(tr -d '[:space:]' < "${next_version_repo}/version")"
  base_release_version="$(printf '%s' "${next_version}" | sed -E 's/-rc\.[0-9]+$//')"
  capi_version="${base_release_version}-rc (${capi_release_short_ref})"
fi

echo "cf_deployment_version: ${cf_deployment_version}" >> "${cf_versions_output}/cf_versions.yml"
echo "capi_version: ${capi_version}" >> "${cf_versions_output}/cf_versions.yml"

cat "${cf_versions_output}/cf_versions.yml"
