#!/bin/bash

set -euo pipefail

task_root="$(pwd)"
cf_perf_tests_pipeline_repo="${task_root}/cf-performance-tests-pipeline"
bbl_state="${task_root}/bbl-state/${BBL_STATE_DIR}"

prune_released_rc_results() {
  local test_dir
  local newest_result_file
  local newest_capi_version
  local released_base_version
  local deleted=0

  # Find all test result directories and iterate over them.
  while IFS= read -r test_dir; do

    # Retention policy per test folder: if newest result has a release capi-version "X.Y.Z (sha)",
    # prune older "X.Y.Z-rc (sha)" files in that same folder.
    newest_result_file="$({
      find "$test_dir" -maxdepth 1 -type f -name '*.json' -print |
        awk '
          {
            ts = 0
            if (match($0, /-[0-9]+\.json$/)) {
              # match gives "-<digits>.json"; strip leading "-" and trailing ".json".
              ts = substr($0, RSTART + 1, RLENGTH - 6)
            }
            # Sort newest first by embedded filename timestamp.
            printf("%012d\t%s\n", ts, $0)
          }
        ' |
        sort -r |
        cut -f2- |
        head -n 1
    } || true)"

    if [[ -z "$newest_result_file" ]]; then
      continue
    fi

    newest_capi_version="$(jq -r '.capiVersion // ""' "$newest_result_file" 2>/dev/null || true)"
    # Matches released versions like: "1.249.0 (f83f4a3)"; does not match RC forms.
    released_base_version="$(printf '%s' "$newest_capi_version" | sed -nE 's/^([0-9]+\.[0-9]+\.[0-9]+) \(([0-9a-f]{7,40})\)$/\1/p')"

    # If newest file in this test folder is RC (or legacy/unknown), do not purge old results.
    if [[ -z "$released_base_version" ]]; then
      continue
    fi

    # Newest file is a released version -> scan newest-to-oldest and purge
    # matching RC results until an older released base version boundary.
    while IFS= read -r result_file; do
      local capi_version
      local rc_base_version
      local older_released_base_version

      capi_version="$(jq -r '.capiVersion // ""' "$result_file" 2>/dev/null || true)"
      rc_base_version="$(printf '%s' "$capi_version" | sed -nE 's/^([0-9]+\.[0-9]+\.[0-9]+)-rc \(([0-9a-f]{7,40})\)$/\1/p')"
      older_released_base_version="$(printf '%s' "$capi_version" | sed -nE 's/^([0-9]+\.[0-9]+\.[0-9]+) \(([0-9a-f]{7,40})\)$/\1/p')"

      if [[ -n "$older_released_base_version" && "$older_released_base_version" != "$released_base_version" ]]; then
        break
      fi

      if [[ "$rc_base_version" == "$released_base_version" ]]; then
        rm -f "$result_file"
        deleted=$((deleted + 1))
      fi
    done < <(
      find "$test_dir" -maxdepth 1 -type f -name '*.json' -print |
        awk '
          {
            ts = 0
            if (match($0, /-[0-9]+\.json$/)) {
              ts = substr($0, RSTART + 1, RLENGTH - 6)
            }
            printf("%012d\t%s\n", ts, $0)
          }
        ' |
        sort -r |
        cut -f2-
    )
  done < <(find "$cf_perf_tests_pipeline_repo/results" -type f -name '*.json' -exec dirname {} \; | sort -u)

  echo "Pruned ${deleted} '-rc (sha)' result files across test folders where newest result is released."
}

echo -e "\nInitializing BOSH environment from bbl state..."
pushd "$bbl_state" >/dev/null
  eval "$(bbl print-env)"
popd >/dev/null

echo -e "\nDownloading test results from errand VM..."
bosh -d cf scp cf-performance-tests-errand/0:/tmp/results.tar.gz "${cf_perf_tests_pipeline_repo}/results.tar.gz"
pushd "$cf_perf_tests_pipeline_repo" >/dev/null
  tar -xzvf results.tar.gz
  rm -rf results.tar.gz
popd >/dev/null

prune_released_rc_results

echo -e "\nInstalling git lfs..."
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
