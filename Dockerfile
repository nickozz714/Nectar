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
ENTRYPOINT ["/start.sh"]
