# ubi9-node-workspace: UBI 9.7 equivalent of `codercom/enterprise-node:ubuntu`.
#
# The Coder template in ../../template FROMs this image. Source upstream that we
# are replacing: docker.io/codercom/enterprise-node (Ubuntu-based, with Node 22,
# npm, yarn, Coder agent prereqs). We rebuild on UBI9 so the workspace runtime
# fits the demo's RHEL story and we control the security posture.
#
# Built and pushed by GitLab CI (Kaniko) on changes under images/**; see
# ../../.gitlab-ci.yml. The CI build overrides WORKSPACE_BASE with the
# ubi9-base-workspace tag the base job just pushed to this project's registry.
#
# Tag scheme (CI_REGISTRY_IMAGE = registry.usgov.coderdemo.io/coderdemo/coder-templates):
#   ${CI_REGISTRY_IMAGE}/ubi9-node-workspace:9.7
#   ${CI_REGISTRY_IMAGE}/ubi9-node-workspace:9.7-<short-sha>
#   ${CI_REGISTRY_IMAGE}/ubi9-node-workspace:latest

ARG WORKSPACE_BASE=registry.usgov.coderdemo.io/coderdemo/coder-templates/ubi9-base-workspace:latest
FROM ${WORKSPACE_BASE}

USER 0

# Node.js 22 LTS via NodeSource RPM (UBI9 ships only Node 18 in default repos;
# NodeSource provides up-to-date LTS streams). yarn + pnpm via corepack.
RUN curl -fsSL https://rpm.nodesource.com/setup_22.x | bash - \
    && dnf install -y --nodocs --setopt=install_weak_deps=False nodejs \
    && dnf clean all \
    && rm -rf /var/cache/dnf \
    && corepack enable yarn pnpm

# Common npm globals expected by Coder workspace startup scripts.
RUN npm install --global --no-fund --no-audit \
        typescript \
    && rm -rf /root/.npm

# C++ build tooling, pre-installed here so C++-flavored workspace consumers do
# not have to `dnf install` at workspace startup. Faster cold starts, and on a
# locked-down pod the agent's startup script cannot `sudo dnf install` anyway.
#
# Package notes:
#   - `gcc` + `make` are already in ubi9-base-workspace; we add `clang` as an
#     alternate compiler and `gdb` for debugging.
#   - `clang-tools-extra` provides `clangd`, the LSP server VSCode / code-server
#     uses for C++ IntelliSense.
#   - `pkg-config` on UBI9 is packaged as `pkgconf-pkg-config` (the pkgconf
#     reimplementation provides the `pkg-config` binary via a compat shim).
#     Plain `pkg-config` is NOT a valid package name on UBI9.
RUN dnf install -y --nodocs --setopt=install_weak_deps=False \
        cmake \
        gdb \
        clang \
        clang-tools-extra \
        pkgconf-pkg-config \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# Re-apply group-0 home perms after the root-owned installs above (anything
# that touched /home/coder needs to stay group-writable).
RUN chgrp -R 0 /home/coder \
    && chmod -R g=u /home/coder

USER 1001
WORKDIR /home/coder

CMD ["sleep", "infinity"]
