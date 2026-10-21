#!/bin/bash

set -euo pipefail

task_root="$(pwd)"
results_repo="${task_root}/results"
capi_release_repo="${task_root}/capi-release-ci-passed"
bbl_state="${task_root}/bbl-state/${BBL_STATE_DIR}"

# This job only deals with "rails" results for a single CCDB (e.g. postgres15),
# so scope pruning and committing to that database's subtree.
results_dir="${results_repo}/results/rails/${CCDB}"

prune_released_rc_results() {
  local deleted=0
  declare -A released_versions=()

  # Build the set of released versions from capi-release git tags (e.g. "1.249.0").
  # The capi-release-ci-passed resource uses `fetch_tags: true` so tags are available locally.
  local tag
  while IFS= read -r tag; do
    [[ -n "$tag" ]] && released_versions["$tag"]=1
  done < <(git -C "$capi_release_repo" tag -l 2>/dev/null | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' || true)

  # Safety net: never prune based on an empty released set.
  if [[ ${#released_versions[@]} -eq 0 ]]; then
    echo "No released capi-release tags found; skipping RC pruning."
    return
  fi

  # Delete any "X.Y.Z-rc[.N]? (sha)" result file whose base version X.Y.Z is released.
  local result_file
  local capi_version
  local rc_base_version
  while IFS= read -r result_file; do
    capi_version="$(jq -r '.capiVersion // ""' "$result_file" 2>/dev/null || true)"
    rc_base_version="$(printf '%s' "$capi_version" | sed -nE 's/^([0-9]+\.[0-9]+\.[0-9]+)-rc(\.[0-9]+)? \([0-9a-f]{7,40}\)$/\1/p')"

    if [[ -n "$rc_base_version" && -n "${released_versions[$rc_base_version]:-}" ]]; then
      rm -f "$result_file"
      deleted=$((deleted + 1))
    fi
  done < <(find "$results_dir" -type f -name '*.json')

  echo "Pruned ${deleted} '-rc (sha)' result files for released versions."
}

echo -e "\nInitializing BOSH environment from bbl state..."
pushd "$bbl_state" >/dev/null
  eval "$(bbl print-env)"
popd >/dev/null

echo -e "\nDownloading test results from errand VM..."
bosh -d cf scp cf-performance-tests-errand/0:/tmp/results.tar.gz "${results_repo}/results.tar.gz"
pushd "$results_repo" >/dev/null
  tar -xzvf results.tar.gz
  rm -rf results.tar.gz
popd >/dev/null

prune_released_rc_results

echo -e "\nInstalling git lfs..."
apt-get update && apt-get -y install git-lfs
git lfs install

if [[ $(git -C "$results_repo" status --porcelain -- "$results_dir") ]]; then
  echo -e "\nCommitting test results..."
  git -C "$results_repo" config user.name "$GIT_COMMIT_USERNAME"
  git -C "$results_repo" config user.email "$GIT_COMMIT_EMAIL"
  git -C "$results_repo" add --all "$results_dir"
  git -C "$results_repo" commit -m "$GIT_COMMIT_MESSAGE"
fi

echo -e "\nFinished."
