# CLAUDE.md

Guidance for agents and engineers working in the `usgov-coderdemo` repository.
This file is intentionally lean; the deep material lives under `docs/`.

## Repository map

- `STATUS.md` is the single source of progress truth.
- `docs/as-built/` is the engineering as-built documentation (architecture,
  configuration, the declarative-vs-imperative ledger).
- `deploy/` holds the Kubernetes manifests and Helm values for every component.
- `scripts/` holds the idempotent setup and verification scripts.
- `terraform/` holds the AWS substrate.
- `docs/envdocs/` is the MkDocs Material source for the published environment
  docs site (see below).

## Documentation policy (MUST follow)

The full policy is [`docs/DOCS-POLICY.md`](docs/DOCS-POLICY.md). The essentials:

- **Docs are code.** The environment documentation is authored in MkDocs under
  `docs/envdocs/` and published to `https://envdocs.usgov.coderdemo.io`, gated by
  Keycloak SSO to any authenticated user in realm `coder` (no group restriction).
- **Same-change rule.** ANY change to infrastructure, configuration, scripts, or
  templates MUST update the corresponding documentation in the same change. A PR
  that changes behavior without updating the matching page (under `docs/envdocs/`
  or `docs/as-built/`) is incomplete.
- **Single source of truth.** `docs/envdocs/` is the only source for the site.
  The `envdocs-site` ConfigMap and the served HTML are generated from it by
  `scripts/setup-envdocs.py`; never hand-edit cluster state.

## Validate the docs before you push

```sh
make docs-check     # see docs/DOCS-POLICY.md for the target; builds --strict
```

`docs-check` builds the MkDocs site in strict mode, so broken navigation,
dangling internal links, or a malformed config fail the build. Mermaid diagram
syntax should additionally be checked with the Mermaid CLI when diagrams change
(see `docs/DOCS-POLICY.md`).

## Conventions

- No emdash (U+2014), endash (U+2013), or a spaced double-hyphen sequence in
  code, comments, strings, or docs. Use commas, semicolons, or periods.
- Inside Mermaid diagrams, avoid `;` in node and message text: Mermaid treats it
  as a statement separator. Use commas or periods instead.
- Secrets live in AWS Secrets Manager and sync via ESO. Never commit secret
  material; only `deploy/*/secrets.example.yaml` placeholders are committed.
- Images are mirrored into ECR (no pull-through cache in GovCloud). Pin tags.
