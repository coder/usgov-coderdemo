#!/bin/bash
# S2I-style UID entrypoint.
#
# If the pod is started with a UID that has no /etc/passwd entry, then:
#   - Go's os/user.Current() fails with
#     "user: Current requires cgo or $USER set in environment"
#   - HOME defaults to "/" because nss-based home lookup misses
#   - sudo, ssh-keygen, npm, etc. silently misbehave
#
# Append a passwd entry for the runtime UID at startup so all of the above
# behave normally. Requires the image to have made /etc/passwd group-writable
# (mode g=u, group root); see the Dockerfile. On this EKS demo the pod runs as
# uid 1001, which already has a passwd entry, so the append is a no-op and the
# entrypoint just normalizes HOME/USER and execs the command.

set -e

USER_ID=$(id -u)

if ! getent passwd "${USER_ID}" >/dev/null 2>&1; then
  echo "coder:x:${USER_ID}:0:Coder user:/home/coder:/bin/bash" >> /etc/passwd 2>/dev/null || true
fi

export HOME=/home/coder
export USER=coder

# When invoked with no args (e.g., `kubectl exec -it`), drop into bash;
# otherwise exec the requested command. Coder workspace pods pass
# `["sh","-c", coder_agent.main.init_script]`, so the exec path is the normal
# one.
if [ "$#" -eq 0 ]; then
  exec /bin/bash
fi
exec "$@"
