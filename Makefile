SHELL := /bin/bash
TF := terraform -chdir=terraform
export AWS_PROFILE ?= demoenv-usgov
export AWS_REGION ?= us-gov-west-1

.PHONY: help fmt init plan apply destroy mirror kubeconfig

help: ## Show targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-12s %s\n", $$1, $$2}'

fmt: ## terraform fmt
	$(TF) fmt -recursive

init: ## terraform init
	$(TF) init

plan: ## terraform plan
	$(TF) plan

apply: ## terraform apply
	$(TF) apply

destroy: ## terraform destroy (tears the demo down)
	$(TF) destroy

mirror: ## Mirror upstream images into ECR
	./scripts/mirror-images.sh

kubeconfig: ## Write kubeconfig for the EKS cluster
	aws eks update-kubeconfig --name usgov-coderdemo --region $(AWS_REGION)
