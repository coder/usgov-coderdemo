# OCP fabric rebuild

OCP is a rebuildable workspace fabric. Control plane on EKS is unaffected.

## When

- OCP cluster corrupt or upgrade needed
- WS-11a IPI failed partially

## Steps

1. Confirm Coder CP at `dev.usgov.coderdemo.io` still healthy (C1)
2. `terraform destroy` or reinstall via `terraform/ocp/` (WS-11a)
3. Expect ~75 min IPI
4. Re-run WS-11c (provisioner), WS-11d (proxy), WS-11f (template)
5. Validate C6, C7

## Preserve

- EKS control plane, RDS, templates for `platform=eks`
- GitOps manifests in repo (gitops/, manifests/)
