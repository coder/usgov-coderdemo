#!/bin/sh
# Sets the mcp_ro role password from the MCP_RO_PASSWORD environment variable
# (injected from the ESO-synced demo-db-secret). This runs after seed.sql during
# Postgres initialization, so the credential is never stored as a literal in git.
# The postgres entrypoint sources non-executable *.sh files in
# /docker-entrypoint-initdb.d after the *.sql files, in filename order, so this
# "zz-" prefixed script runs last (after seed.sql creates the role).
psql -v ON_ERROR_STOP=1 --username "${POSTGRES_USER:-postgres}" --dbname "${POSTGRES_DB:-demo}" \
  -c "ALTER ROLE mcp_ro PASSWORD '${MCP_RO_PASSWORD}';"
