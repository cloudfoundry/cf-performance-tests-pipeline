#!/bin/bash

export SYSTEM_DOMAIN=cf.cfperftest.<your domain>
bosh deploy -d cf cf-deployment/cf-deployment.yml \
  -v system_domain=$SYSTEM_DOMAIN \
  -o cf-deployment/operations/use-postgres.yml \
  -o operations/use-bionic-stemcell.yml \
  --no-redact