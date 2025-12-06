# Dockerfile for DocPilot with GPU support (NVIDIA CUDA runtime)
# NOTE: This image provides a runtime with CUDA available. It installs
# Python and system dependencies required by the project. Heavy model
# downloads will occur at runtime or during pip install - they are not
# embedded as pre-downloaded artifacts here.

FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies including Tesseract OCR and multimedia libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    wget \
    curl \
    ca-certificates \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt /app/requirements.txt
# For the Linux container we avoid installing the macOS-only 'mlx-vlm' package
# because it pulls in Python bindings expecting native macOS libs (libmlx.so),
# which cause runtime ImportError when used on Linux. Create a filtered
# requirements file that excludes mlx-vlm and install from that.
RUN pip install --upgrade pip setuptools wheel && \
    grep -v "^mlx-vlm" /app/requirements.txt > /app/requirements_no_mlx.txt && \
    pip install --no-cache-dir -r /app/requirements_no_mlx.txt

# Copy project files
COPY . /app

# Path where model artifacts can be mounted to avoid repeated downloads
ENV DOCLING_ARTIFACTS_PATH=/artifacts
ENV PORT=8501

EXPOSE 8501

# Create entrypoint wrapper inside the image and make it executable (avoid separate file)
RUN cat > /app/run.sh << 'EOF'
#!/usr/bin/env sh
# Startup wrapper: if mounted /artifacts does not contain expected RapidOCR models,
# unset DOCLING_ARTIFACTS_PATH so Docling/RapidOCR will fall back to its default
# artifact download/cache behavior. This avoids hard-failing when an empty
# /artifacts mount is provided.

set -e

REQUIRED_MODEL="/artifacts/RapidOcr/torch/PP-OCRv4/det/ch_PP-OCRv4_det_infer.pth"

echo "[entrypoint] checking for pre-fetched artifacts..."
if [ -f "$REQUIRED_MODEL" ]; then
    echo "[entrypoint] found RapidOCR model at $REQUIRED_MODEL — using /artifacts as DOCLING_ARTIFACTS_PATH"
else
    echo "[entrypoint] RapidOCR model not found at $REQUIRED_MODEL"
    if [ -d "/artifacts" ] && [ "$(ls -A /artifacts)" ]; then
        echo "[entrypoint] /artifacts exists but appears incomplete — unsetting DOCLING_ARTIFACTS_PATH to allow automatic downloads"
    else
        echo "[entrypoint] /artifacts missing or empty — unsetting DOCLING_ARTIFACTS_PATH to allow automatic downloads"
    fi
    unset DOCLING_ARTIFACTS_PATH
fi

echo "[entrypoint] starting Streamlit..."
exec streamlit run app.py --server.port 8501 --server.address 0.0.0.0
EOF

RUN chmod +x /app/run.sh

# Run Streamlit via wrapper
CMD ["/app/run.sh"]
