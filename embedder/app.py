from __future__ import annotations

import os

from fastapi import FastAPI
from fastembed import TextEmbedding
from pydantic import BaseModel

# Local-first: the model is baked into the image at build time; no cloud, no runtime
# internet. Multilingual by default — hive memories are written in Dutch and English.
MODEL_NAME = os.environ.get(
    "EMBEDDER_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
model = TextEmbedding(MODEL_NAME)

app = FastAPI(title="HiveMind embedder")


class EmbedRequest(BaseModel):
    model: str | None = None  # accepted for OpenAI compatibility; the local model is used
    input: str | list[str]


@app.post("/v1/embeddings")
def embeddings(body: EmbedRequest):
    texts = [body.input] if isinstance(body.input, str) else body.input
    vectors = model.embed(texts)
    return {
        "object": "list",
        "model": MODEL_NAME,
        "data": [
            {"object": "embedding", "index": i, "embedding": v.tolist()}
            for i, v in enumerate(vectors)
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok", "model": MODEL_NAME}
