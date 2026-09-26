# ── LocalDocQA Dockerfile ─────────────────────────────────────────────────────
#
# REPAIRED by Bob (EgressProof repair agent):
#   The sentence-transformers model is now downloaded INTO the image during
#   the build step below, so it is available offline at runtime.
#   TRANSFORMERS_OFFLINE=1 and HF_DATASETS_OFFLINE=1 prevent any attempt
#   to contact huggingface.co at runtime.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only PyTorch first to avoid pulling the ~2 GB CUDA variant.
# sentence-transformers will reuse this torch installation.
RUN pip install --no-cache-dir \
    torch==2.3.1+cpu \
    --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Point HuggingFace / sentence-transformers cache to a container-internal path.
ENV TRANSFORMERS_CACHE=/app/models
ENV HF_HOME=/app/models

RUN mkdir -p /app/models

# ── REPAIR: bake the embedding model into the image at build time ─────────────
# This download happens while the builder still has internet access.
# At runtime the model is already on disk and no outbound connection is needed.
RUN python - <<'EOF'
from sentence_transformers import SentenceTransformer
SentenceTransformer("all-MiniLM-L6-v2")
print("Model downloaded successfully into /app/models")
EOF

# Disable all HuggingFace Hub network access at runtime so the app never
# attempts to reach huggingface.co, even for cache-freshness checks.
ENV TRANSFORMERS_OFFLINE=1
ENV HF_DATASETS_OFFLINE=1

# Copy application source
COPY backend/ .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
