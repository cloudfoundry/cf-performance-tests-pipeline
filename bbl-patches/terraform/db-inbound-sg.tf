# required for ssh tunnel to postgres db over jumpbox
resource "aws_security_group_rule" "internal_security_group_rule_db_tunnel" {
  security_group_id        = "${aws_security_group.internal_security_group.id}"
  type                     = "ingress"
  protocol                 = "TCP"
  from_port                = 5524
  to_port                  = 5524
  source_security_group_id = "${aws_security_group.jumpbox.id}"
}

# required for ssh tunnel to MySQL db over jumpbox
resource "aws_security_group_rule" "internal_security_group_rule_mysql_db_tunnel" {
  security_group_id        = "${aws_security_group.internal_security_group.id}"
  type                     = "ingress"
  protocol                 = "TCP"
  from_port                = 3306
  to_port                  = 3306
  source_security_group_id = "${aws_security_group.jumpbox.id}"
}
