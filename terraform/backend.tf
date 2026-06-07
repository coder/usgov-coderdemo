terraform {
  backend "s3" {
    bucket         = "usgov-coderdemo-tfstate-430737322961"
    key            = "demo/terraform.tfstate"
    region         = "us-gov-west-1"
    dynamodb_table = "usgov-coderdemo-tflock"
    encrypt        = true
  }
}
