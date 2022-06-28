# Manual Setup

This protocol can be used as a base for creating an automation.

### Load Balancer Certificate

Create a config file for the certificate:
```
# server_rootCA.csr.cnf
[req]
default_bits = 2048
prompt = no
default_md = sha256
distinguished_name = dn
req_extensions = req_ext

[dn]
C=<Country>
ST=<City>
L=<Province>
O=<Organisation>
OU=<Organization Unit>
CN = *.cf.cfperftest.<your domain>

[req_ext]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.0 = *.cfapps.cfperftest.<your domain>
DNS.1 = *.login.cfperftest.<your domain>
DNS.2 = *.uaa.cfperftest.<your domain>
```

Create a self-signed certificate with:
```
openssl req -x509 -sha256 -nodes -out cert.pem -newkey rsa:2048 -keyout key.pem -days 365 -config server_rootCA.csr.cnf -extensions req_ext
```

### Docker Tools Container

The [cf-deployment-concourse-tasks](https://github.com/cloudfoundry/cf-deployment-concourse-tasks) Docker image contains all required CLI tools. Assuming that this repo is cloned into ~/cf/cf-performance-tests-pipeline, start a Docker container with:
```
docker pull cloudfoundry/cf-deployment-concourse-tasks
docker run -it -v ~/cf/cf-performance-tests-pipeline:/home/cfperftest cloudfoundry/cf-deployment-concourse-tasks
```

### AWS Account Setup

Create a AWS user with name **iaas-provider_bootstrap-cfperftest** and permissions "AdminsGroup / AdministratorAccess".

Save credentials in a secure place.

### BBL Setup

Create a load balancer, the jumpbox and bootstrap-bosh with bbl:
```
bbl --state-dir ./state plan --lb-type cf --lb-domain cf.cfperftest.<your domain> --lb-cert cert.pem --lb-key key.pem --iaas aws --aws-access-key-id <ACCESS_KEY_ID> --aws-secret-access-key <ACCESS_KEY_SECRET> --aws-region eu-central-1
bbl --debug --state-dir ./state up --aws-access-key-id <ACCESS_KEY_ID> --aws-secret-access-key <ACCESS_KEY_SECRET>
```

You should now be able to access the jumpbox and the BOSH director:
```
bbl ssh --jumpbox
bbl ssh --director
```

Log on to the BOSH director should also work now:
```
eval "$(bbl print-env)"
bosh releases
```

### Adjust ELB Idle Timeout

The AWS ELB has a default idle timeout of 60 seconds. This can be too short for long-running tests. You can receive a 504 response if the CF cloud controller takes longer than 60 seconds to respond:
```
$ cf curl -v /v3/service_plans 

REQUEST: [2021-11-23T10:37:09Z]
GET /v3/service_plans HTTP/1.1
Host: api.cf.cfperftest.bndl.sapcloud.io
Accept: application/json
Authorization: [PRIVATE DATA HIDDEN]
Content-Type: application/json
User-Agent: go-cli 7.3.0+645c3ce6a.2021-08-16 / linux


RESPONSE: [2021-11-23T10:38:42Z]
HTTP/1.1 504 GATEWAY_TIMEOUT
Connection: close
Content-Length: 0
```
To adjust the timeout, we need a [Terraform override file](https://www.terraform.io/docs/language/files/override.html) which modifies the "cf_router_lb" resource. Create this file:
```
# elb-idle-timeout_override.tf

resource "aws_elb" "cf_router_lb" {
  idle_timeout = 300
}
```
Place the file in the `state/terraform` folder. The next run of `bbl plan` and `bbl up` will apply the configuration. You can verify the configuration in the AWS console in "EC2" > "Load Balancers" > "bbl-env-<env name>-cf-router-lb" > "Attributes" > "Idle timeout".

### Upload State

Now you must persist the state. As it contains credentials, it cannot be stored in git. Instead, we store it in a S3 bucket with special permissions.

Create a tgz file of the state with:
```
tar -czvf bbl-state.tar.gz state
```
The archive must contain the "state" folder as the top-level content. It should be around 160kb in size. If it is several mb large, it probably contains unnecessary Terraform binaries. In that case, search for a ".terraform" folder with a "plugins" subfolder and remove it. Also make sure you are running the tar command in the Docker container and not locally on a Mac. The Mac "tar" command may add additional meta files which can lead to problems.

Upload the tgz file to the S3 bucket "cf-perf-test-state" or "go-perf-test-state".

### DNS Setup

Get the name servers from "state/vars/terraform.tfstate":
```
"name_servers.0": "some.domain.com"
"name_servers.1": "some.domain.com"
"name_servers.2": "some.domain.com"
"name_servers.3": "some.domain.com"
```

Go to your domain service, and create the following entry for your domain:

* Record name: "cf.cfperftest"
* Record type: "NS - Name servers for a hosted zone"
* Value: (the 4 "ns-..." entries from above)

### BOSH Setup

The "dns" runtime-config should already have been uploaded, check with:
```
bosh configs
```

Upload stemcell:
```
export IAAS_INFO=aws-xen-hvm
bosh upload-stemcell https://storage.googleapis.com/bosh-core-stemcells/1.13/bosh-stemcell-1.13-aws-xen-hvm-ubuntu-bionic-go_agent.tgz
```

### S3 Blobstore Setup (optional)

By default, cf-deployment uses a single-node WebDAV blobstore. It shows up as `singleton-blobstore` in the list of VMs. If it turns out that the WebDAV blobstore is a bottleneck for certain performance tests, you can also use a S3 blobstore instead.

In AWS IAM, create a new S3 user for the blobstore access. Attach the policy "AmazonS3FullAccess". Store the access key id and the secret key in CredHub. The "credhub" CLI should already be ready to use, see [BBL Setup](#bbl-setup).
```
credhub set -n /blobstore-cfperftest/access_key_id -t password -w <ACCESS_KEY_ID>
credhub set -n /blobstore-cfperftest/access_secret_id -t password -w <ACCESS_KEY_SECRET>
```
These credentials are referenced in [variables/vars-use-s3-blobstore.yml](variables/vars-use-s3-blobstore.yml).

Now create the S3 buckets. Use the default settings, but enable "Server-side encryption" with "Amazon S3 key". Create 4 buckets:

* cfperftest-buildpacks
* cfperftest-droplets
* cfperftest-packages
* cfperftest-resources

Add the following vars and ops files to the deployment script:

```
  --vars-file=operations/vars-use-s3-blobstore.yml \	
  -o cf-deployment/operations/use-external-blobstore.yml \
  -o cf-deployment/operations/use-s3-blobstore.yml \
```

### Cloud Controller Database

The default database for a cf-deployment installation is a MySQL Galera cluster. To use Postgres instead, simply add this ops file:
https://github.com/cloudfoundry/cf-deployment/blob/main/operations/use-postgres.yml

### Deployment of CF

Clone the desired version of cf-deployment into this project's root:
```
git clone https://github.com/cloudfoundry/cf-deployment.git
```
Now we are ready to deploy CF. Execute the [scripts/deploy_cf.sh](scripts/deploy_cf.sh) script. It generates the manifest using a few ops and vars files and then triggers the BOSH deployment. When the deployment has finished, you should be able to access the CF API:
```
curl -k https://api.cf.cfperftest.<your domain>/v2/info
```

### Manual Destruction

To manually delete everything, first delete the CF deployment (and all other deployments, if any):
```
bosh -d cf delete-deployment
```

Now use bbl to destroy all infrastructure resources:
```
bbl --debug --state-dir ./state destroy --aws-access-key-id <ACCESS_KEY_ID> --aws-secret-access-key <ACCESS_KEY_SECRET> --aws-region eu-central-1
```
After successful deletion the "state" folder should be empty again and MUST be commited.

Finally, delete the DNS configuration that was created in step [DNS Setup](#dns-setup).