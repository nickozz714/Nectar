#!/bin/bash
# Single-container startup: Neo4j in the background via its stock entrypoint
# (drops privileges itself), then the API. init_db() retries until bolt is up.
set -e

export NEO4J_AUTH="neo4j/${NEO4J_PASSWORD:?NEO4J_PASSWORD not set}"
export NEO4J_URI="${NEO4J_URI:-bolt://localhost:7687}"
export NEO4J_USER="${NEO4J_USER:-neo4j}"

# The Neo4j entrypoint turns every NEO4J_* env var into a config setting; strip the
# ones that are only meant for the Python client or Neo4j refuses to start.
env -u NEO4J_URI -u NEO4J_USER -u NEO4J_PASSWORD /startup/docker-entrypoint.sh neo4j &

cd /app
exec uvicorn src.main:app --host 0.0.0.0 --port 8000
