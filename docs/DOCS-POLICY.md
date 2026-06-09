# Documentation policy

This repository treats documentation as code. The environment is documented in
MkDocs and published as a gated, in-boundary website. This policy is mandatory.

## Where docs live and how they are published

- **Source:** the published site is authored in MkDocs Material under
  `docs/envdocs/` (config `docs/envdocs/mkdocs.yml`, pages
  `docs/envdocs/docs/*.md`). This is the single source of truth for the site.
- **Engineering detail:** the deeper, file-grounded as-built documentation lives
  under `docs/as-built/`. The `docs/envdocs/` site curates and summarizes it for
  readers; it does not replace it.
- **Published at:** `https://envdocs.usgov.coderdemo.io`.
- **Access:** gated by Keycloak SSO (realm `coder`) through oauth2-proxy and
  ingress-nginx external-auth. **Any authenticated realm `coder` user** can read
  the site, with no group restriction. Unauthenticated requests are redirected to
  `https://auth.usgov.coderdemo.io`. See
  `docs/envdocs/docs/access-and-auth.md` and `deploy/envdocs/`.
- **Build and serve:** `scripts/setup-envdocs.py` generates the `envdocs-site`
  ConfigMap from `docs/envdocs/` and applies `deploy/envdocs/`. An init container
  runs `mkdocs build` in-cluster from the ConfigMap; nginx serves the result. The
  script is idempotent.

## The same-change rule (mandatory)

Any change to infrastructure, configuration, scripts, or templates MUST update
the corresponding documentation in the **same change** (commit or PR). This
includes, at minimum:

| If you change | Update |
|---|---|
| `deploy/coder/**`, Coder env/Helm | `docs/envdocs/docs/coder-control-plane.md` (and `docs/as-built/30-*.md`) |
| `deploy/keycloak/**`, realm, IdP sync, `scripts/setup-*idp*`, `scripts/setup-keycloak-hierarchy.py` | `docs/envdocs/docs/identity-keycloak.md` (and `docs/as-built/40-*.md`, `45-*.md`) |
| `deploy/gitlab/**`, GitLab OAuth/CI | `docs/envdocs/docs/gitlab.md` (and `docs/as-built/50-*.md`) |
| AI Gateway providers, `deploy/coder` AI env | `docs/envdocs/docs/ai-gateway.md` (and `docs/as-built/60-*.md`) |
| `deploy/observability/**`, dashboards | `docs/envdocs/docs/observability.md` (and `docs/as-built/55-*.md`) |
| `deploy/platform/external-secrets/**`, ASM layout | `docs/envdocs/docs/secrets.md` (and `docs/as-built/85-*.md`) |
| `deploy/envdocs/**`, `scripts/setup-envdocs.py` | `docs/envdocs/docs/access-and-auth.md` |
| Demo flow, personas, org changes | `docs/envdocs/docs/demo-runbook.md` |

A PR that changes behavior without the matching doc update is incomplete and
should not merge.

## Validation: `make docs-check`

Build the site in strict mode before pushing. Strict mode fails on broken
navigation, dangling internal links, or a malformed config.

Add this target to the repository root `Makefile` (the file is not part of this
change; add the snippet there):

```makefile
docs-check: ## Build the envdocs MkDocs site in strict mode
	cd docs/envdocs && mkdocs build --strict --site-dir /tmp/envdocs-site-check
```

Then run:

```sh
make docs-check
```

Requires `mkdocs-material` (the same package the in-cluster build image
provides). Install locally with `pip install mkdocs-material` if needed.

### Mermaid diagrams

When you add or change a Mermaid diagram, validate it renders. `mkdocs build`
does not catch Mermaid syntax errors (they render client-side). Use the Mermaid
CLI:

```sh
npx -y @mermaid-js/mermaid-cli@11 -i diagram.mmd -o /tmp/diagram.svg
```

Reminder: Mermaid treats `;` as a statement separator, so do not put `;` in node
or message text. Use commas or periods.

## Authoring conventions

- No emdash (U+2014), endash (U+2013), or a spaced double-hyphen sequence
  anywhere in the docs. Use commas, semicolons, or periods.
- Keep content grounded in repo files (`deploy/**`, `scripts/**`, `STATUS.md`,
  `docs/as-built/**`). Prefer real config snippets over invented examples.
- Never include secret values. Reference secret names and keys only.
