# ubi9-base-workspace: UBI 9.7 + dev tooling for Coder workspaces.
#
# Used as the FROM for ubi9-node-workspace (the Node-flavored sibling that
# replaces upstream codercom/enterprise-node:ubuntu). The Coder template in
# ../../template consumes ubi9-node-workspace, not this base directly.
#
# Group-0 home perms (the Red Hat S2I pattern). The home dir is made
# group-writable by GID 0 (the root group):
#
#   chgrp -R 0 /home/coder
#   chmod -R g=u /home/coder
#
# On OpenShift the restricted-v2 SCC injects a random UID and adds GID 0 as a
# supplemental group, so the injected UID can read/write home. On this EKS demo
# we run the pod with securityContext run_as_user=1001, run_as_group=0,
# fs_group=0 (see ../../template/main.tf), which lands on the same group-0,
# group-writable home, so the Coder agent and /home/coder behave the same way.
#
# Built and pushed by GitLab CI (Kaniko) on changes under images/**; see
# ../../.gitlab-ci.yml.
#
# Tag scheme (CI_REGISTRY_IMAGE = registry.usgov.coderdemo.io/coderdemo/coder-templates):
#   ${CI_REGISTRY_IMAGE}/ubi9-base-workspace:9.7
#   ${CI_REGISTRY_IMAGE}/ubi9-base-workspace:9.7-<short-sha>
#   ${CI_REGISTRY_IMAGE}/ubi9-base-workspace:latest
#
# UBI minor pinned for reproducibility; bump when Red Hat ships a new minor
# (currently RHEL 9.7). Pulled directly from registry.access.redhat.com (UBI is
# freely redistributable, anonymous pull) because the gitlab-runner namespace
# has internet egress.
FROM registry.access.redhat.com/ubi9/ubi:9.7

ARG USER=coder
ARG UID=1001

# Core dev tooling + dotfiles deps.
#
# `curl` is intentionally NOT in the AppStream list. UBI9 ships
# `curl-minimal`, which provides the curl binary and conflicts with the full
# curl package.
#
# zsh / tmux / neovim / fzf / ripgrep / fd-find / starship are pre-installed so
# the dotfiles repo's install.sh `install_if_missing` checks short-circuit.
#
# fzf / ripgrep / fd-find / xclip live in EPEL on UBI9, so we enable EPEL once
# and install them in a single transaction.
# 1) Enable EPEL as its own layer so metadata is refreshed for the next RUN.
#    (Combining it with the package install in one RUN failed for `tmux`:
#    dnf's cache from the first transaction did not see the just-added EPEL
#    repo.)
RUN dnf install -y --nodocs --setopt=install_weak_deps=False \
        https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm \
    && dnf makecache --refresh

# 2) Tools available in UBI9 BaseOS / AppStream + EPEL.
RUN dnf install -y --nodocs --setopt=install_weak_deps=False \
        bash-completion \
        ca-certificates \
        fd-find \
        fzf \
        gcc \
        git \
        gnupg2 \
        iptables-nft \
        jq \
        less \
        make \
        neovim \
        openssh-clients \
        procps-ng \
        python3.11 \
        python3.11-pip \
        ripgrep \
        sudo \
        tar \
        unzip \
        vim-enhanced \
        wget \
        which \
        zip \
        zsh \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# 3) tmux is not in any UBI9 repo. UBI9 stripped tmux from the redistributable
#    subset and EPEL 9 does not ship it either (only `tmux-powerline`). It IS in
#    upstream RHEL 9's BaseOS, which Rocky Linux mirrors verbatim, so pull the
#    Rocky 9 BaseOS RPM directly. Same ABI, same source, no extra repo setup.
#    Bump the version when Rocky ships `tmux-3.5a` or later for el9.
RUN dnf install -y --nodocs \
        https://download.rockylinux.org/pub/rocky/9/BaseOS/x86_64/os/Packages/t/tmux-3.2a-5.el9.x86_64.rpm \
    && dnf clean all \
    && rm -rf /var/cache/dnf

# Starship prompt, used by the dotfiles' .zshrc/.bashrc. Installed at build
# time as root because the install.sh script writes to /usr/local/bin.
RUN curl -fsSL https://starship.rs/install.sh -o /tmp/starship-install.sh \
    && sh /tmp/starship-install.sh --yes --bin-dir /usr/local/bin \
    && rm -f /tmp/starship-install.sh

# Single non-root user (uid 1001). On this EKS demo the pod runs as this uid;
# the named user gives sudo, a real /etc/passwd entry, and HOME.
RUN useradd --uid ${UID} --create-home --shell /bin/bash --user-group ${USER} \
    && echo "${USER} ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/${USER} \
    && chmod 0440 /etc/sudoers.d/${USER}

# Group-0 home perms. GID 0 is the pod's fs_group/run_as_group on EKS (and a
# supplemental group on OpenShift's restricted-v2), so the runtime UID can write
# here.
RUN chgrp -R 0 /home/${USER} \
    && chmod -R g=u /home/${USER}

# Make /etc/passwd group-writable so the entrypoint can append a passwd entry
# for a non-default runtime UID at startup. Same pattern Red Hat uses in their
# s2i base images.
RUN chmod g=u /etc/passwd

# UID entrypoint: fakes a /etc/passwd entry + HOME for the runtime UID, so
# anything that calls `getent passwd $(id -u)` / `os/user.Current()` (the Coder
# agent does both) works even if the pod is run with an unexpected UID.
COPY uid_entrypoint.sh /usr/local/bin/uid_entrypoint
RUN chmod 0755 /usr/local/bin/uid_entrypoint

# Pre-set $SHELL=/usr/bin/zsh so the dotfiles install.sh's `set_default_shell`
# returns early instead of running `sudo chsh`.
ENV SHELL=/usr/bin/zsh

ENTRYPOINT ["/usr/local/bin/uid_entrypoint"]
USER ${UID}
WORKDIR /home/${USER}

CMD ["sleep", "infinity"]
