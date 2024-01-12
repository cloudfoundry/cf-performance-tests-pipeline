#!/bin/bash

set -euo pipefail

cd cf-performance-tests-release
pushd src/cf-performance-tests >/dev/null
  git pull origin main --ff-only
  commit_message="$(git log --format="%h %s" -1)"
popd >/dev/null

if [ -z "$(git status --porcelain=v1 2>/dev/null)" ]; then
  echo "No submodule update to commit."
else
  git add ./src/cf-performance-tests
  git config --global user.name "testname"
  git config --global user.email "test@sap.com"
  git commit -m "$commit_message"
  echo "Updated submodule to $commit_commit_message"
fi