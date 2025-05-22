#!/bin/bash

set -euo pipefail

yq -o yaml <<< "$VARS" > cf-vars-file/cf-vars.yml