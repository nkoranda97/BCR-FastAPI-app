FROM python:3.13-slim

# -----------------------------------------------------------------------------
# Micromamba (Conda) bootstrap – gives us ARM64‑native binaries in one shot
# -----------------------------------------------------------------------------
ARG MAMBA_VERSION=1.5.8
ENV MAMBA_ROOT_PREFIX=/opt/conda \
    PATH=/opt/conda/bin:$PATH \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates bzip2 liblzma-dev \
        build-essential gcc g++ && \
    mkdir -p /tmp/micromamba && \
    cd /tmp/micromamba && \
    curl -L "https://micro.mamba.pm/api/micromamba/linux-aarch64/${MAMBA_VERSION}" -o micromamba.tar.bz2 && \
    tar -xf micromamba.tar.bz2 && \
    mv bin/micromamba /usr/local/bin/ && \
    cd / && \
    rm -rf /tmp/micromamba && \
    micromamba shell init -s bash -p $MAMBA_ROOT_PREFIX && \
    micromamba install -y -n base -c conda-forge -c bioconda \
        python=3.13 \
        uv \
        blast=2.16.0 \
        igblast=1.22.0 \
        muscle=5.1 && \
    micromamba clean -a -y && \
    rm -rf /var/lib/apt/lists/*

# conda packages place binaries in $MAMBA_ROOT_PREFIX/bin, already in PATH
ENV BLASTDB=/app/app/database/blast \
    GERMLINE=/app/app/database/germlines \
    IGDATA=/app/app/database/igblast \
    PYTHONPATH=/app

WORKDIR /app

# -----------------------------------------------------------------------------
# Python dependencies (cached separately via pyproject.toml)
# -----------------------------------------------------------------------------
COPY pyproject.toml ./
RUN uv sync

# Copy rest of application
COPY . .

# Folders used at runtime
RUN mkdir -p instance/uploads instance/blast instance/igblast

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
