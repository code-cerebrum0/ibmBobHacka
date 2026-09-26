"""
LocalDocQA — demo FastAPI application for EgressProof.

Hidden runtime dependency:
    SentenceTransformer("all-MiniLM-L6-v2") is loaded lazily on the first
    POST /ask request.  With internet access this downloads the model from
    huggingface.co and succeeds.  Under network isolation the download fails,
    producing a ConnectionError that is logged and returned as a 503.
"""

import logging
import os
from typing import Dict

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("localdocqa")

app = FastAPI(title="LocalDocQA")

# ── in-memory document store ──────────────────────────────────────────────────
_documents: Dict[str, str] = {}

# ── lazy model handle ─────────────────────────────────────────────────────────
_model = None


def get_model():
    """Return the SentenceTransformer, downloading it on first call."""
    global _model
    if _model is None:
        logger.info("Loading SentenceTransformer model all-MiniLM-L6-v2 ...")
        # Intentional runtime internet dependency — model is NOT baked into image.
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        _model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("Model loaded successfully.")
    return _model


# ── endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    """Accept a .txt file and store its content in memory."""
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Only .txt files are supported.")
    content = await file.read()
    text = content.decode("utf-8")
    _documents[file.filename] = text
    logger.info("Uploaded document: %s (%d chars)", file.filename, len(text))
    return {"filename": file.filename, "chars": len(text), "status": "stored"}


class AskRequest(BaseModel):
    question: str
    filename: str | None = None


@app.post("/ask")
def ask(req: AskRequest):
    """
    Embed the question and all stored document chunks, return the most
    relevant chunk as the answer.

    This endpoint triggers the lazy model load, which requires internet
    access on the first call when the model is not cached locally.
    """
    if not _documents:
        raise HTTPException(status_code=400, detail="No documents uploaded yet.")

    # Select document
    if req.filename:
        if req.filename not in _documents:
            raise HTTPException(status_code=404, detail="Document not found.")
        text = _documents[req.filename]
    else:
        # Use the most recently uploaded document
        text = list(_documents.values())[-1]

    # Split into sentences / chunks (simple newline split)
    chunks = [c.strip() for c in text.split("\n") if c.strip()]
    if not chunks:
        raise HTTPException(status_code=400, detail="Document is empty.")

    try:
        model = get_model()
        query_emb = model.encode([req.question], normalize_embeddings=True)
        chunk_embs = model.encode(chunks, normalize_embeddings=True)
        scores = np.dot(chunk_embs, query_emb.T).flatten()
        best_idx = int(np.argmax(scores))
        answer = chunks[best_idx]
        logger.info("Answered question '%s' → chunk %d", req.question, best_idx)
        return {"question": req.question, "answer": answer, "score": float(scores[best_idx])}
    except Exception as exc:
        # Log the full exception so EgressProof can detect it via container logs.
        logger.error("EGRESS_BLOCKED: Failed to load or run model: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=f"Model unavailable — possible network restriction: {type(exc).__name__}: {exc}",
        )
