# AWS picks a random AZ for subnets without an explicit availability_zone.
# us-east-1e does not support t3.micro, which is used by the jumpbox.
resource "aws_subnet" "bosh_subnet" {
  availability_zone = element(var.availability_zones, 0)
}
