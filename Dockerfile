# All-in-one HiveMind image: Neo4j + API + local embeddings in a single container.
FROM neo4j:5-community

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY server/requirements.txt .
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt
ENV PATH="/opt/venv/bin:$PATH"

# Bake the embedding model into the image: fully offline at runtime, no cloud.
ARG EMBEDDINGS_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ENV EMBEDDINGS_MODEL=$EMBEDDINGS_MODEL
RUN python -c "import os; from fastembed import TextEmbedding; TextEmbedding(os.environ['EMBEDDINGS_MODEL'])"

COPY server/src ./src
# The self-install kit, downloadable from the GUI / GET /install.zip.
COPY hivemind-install.zip ./hivemind-install.zip
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 8000 7474 7687

# Container health = the API answers /health (neo4j + embeddings up). Generous start-period
# because Neo4j boot + embedding warmup take a while on first start.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD /opt/venv/bin/python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health',timeout=3).status==200 else 1)" || exit 1

ENTRYPOINT ["/start.sh"]
