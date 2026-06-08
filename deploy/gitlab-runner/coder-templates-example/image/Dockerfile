# Sample custom workspace image, built by GitLab CI + Kaniko (air-gapped).
#
# BASE_IMAGE points at the project's OWN GitLab Container Registry copy of the
# base, which scripts/setup-gitlab-ci-runners.py pre-seeds from the ECR mirror
# (docker.io/library/debian:bookworm-slim -> ECR -> GitLab CR). Because the base
# lives in the same project registry, the Kaniko build authenticates with only
# the built-in CI job token and pulls nothing from the internet.
#
# The customization below is filesystem-only (no apt/package installs, no
# network egress) so the build stays air-gapped. Swap in your own COPY/RUN steps
# and a richer base (for example the ECR-mirrored codercom/enterprise-base,
# pre-seeded the same way) to produce a real custom workspace image.
ARG BASE_IMAGE=registry.usgov.coderdemo.io/root/coder-templates/workspace-base:bookworm-slim
FROM ${BASE_IMAGE}

LABEL org.coder.demo.image="custom-workspace" \
      org.coder.demo.builder="gitlab-ci + kaniko (air-gapped, unprivileged)"

COPY profile.d/00-coder-custom.sh /etc/profile.d/00-coder-custom.sh

RUN printf 'Custom workspace image built by GitLab CI + Kaniko (air-gapped, unprivileged).\n' \
      > /etc/coder-custom-image
