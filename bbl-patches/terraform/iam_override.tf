resource "aws_iam_policy" "bosh" {
  name = "${var.env_id}_bosh_policy"
  path = "/"

  count = 1 - local.iamProfileCount

  policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": [
        "ec2:AssociateAddress",
        "ec2:AttachVolume",
        "ec2:CopyImage",
        "ec2:CreateVolume",
        "ec2:DeleteSnapshot",
        "ec2:DeleteVolume",
        "ec2:DescribeAddresses",
        "ec2:DescribeAvailabilityZones",
        "ec2:DescribeImages",
        "ec2:DescribeInstances",
        "ec2:DescribeRegions",
        "ec2:DescribeSecurityGroups",
        "ec2:DescribeSnapshots",
        "ec2:DescribeSubnets",
        "ec2:DescribeVolumes",
        "ec2:DetachVolume",
        "ec2:CreateSnapshot",
        "ec2:CreateTags",
        "ec2:ModifyInstanceAttribute",
        "ec2:RunInstances",
        "ec2:TerminateInstances",
        "ec2:RegisterImage",
        "ec2:DeregisterImage",
        "ec2:CancelSpotInstanceRequests",
        "ec2:DescribeSpotInstanceRequests",
        "ec2:RequestSpotInstances",
        "ec2:CreateRoute",
        "ec2:DescribeRouteTables",
        "ec2:ReplaceRoute",
        "ec2:CreateNetworkInterface",
        "ec2:DeleteNetworkInterface",
        "ec2:DescribeNetworkInterfaces",
        "ec2:ModifyNetworkInterfaceAttribute"
	  ],
	  "Effect": "Allow",
	  "Resource": "*"
    },
	{
	  "Action": [
            "iam:PassRole",
            "iam:CreateServiceLinkedRole"
	  ],
	  "Effect": "Allow",
	  "Resource": "*"
	},
	{
	  "Action": [
	    "elasticloadbalancing:*"
	  ],
	  "Effect": "Allow",
	  "Resource": "*"
	},
        {
            "Effect": "Allow",
            "Action": [
                "kms:ReEncrypt*",
                "kms:GenerateDataKey*",
                "kms:CreateGrant",
                "kms:DescribeKey*"
            ],
            "Resource": [
                "*"
            ]
        }
  ]
}
EOF
}
