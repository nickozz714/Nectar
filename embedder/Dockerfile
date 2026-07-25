FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn fastembed

# Bake the model into the image so the stack runs fully offline after build.
ARG EMBEDDER_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
ENV EMBEDDER_MODEL=$EMBEDDER_MODEL
RUN python -c "import os; from fastembed import TextEmbedding; TextEmbedding(os.environ['EMBEDDER_MODEL'])"

COPY app.py .

EXPOSE 8001
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8001"]
