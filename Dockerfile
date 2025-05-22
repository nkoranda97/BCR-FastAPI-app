# Use Python 3.13 slim as base image
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    build-essential \
    libncurses5-dev \
    libncursesw5-dev \
    zlib1g-dev \
    libbz2-dev \
    liblzma-dev \
    cmake \
    git \
    cpio \
    && rm -rf /var/lib/apt/lists/*

# Download and install BLAST+ for ARM64
RUN wget https://ftp.ncbi.nlm.nih.gov/blast/executables/blast+/LATEST/ncbi-blast-2.16.0+-aarch64-linux.tar.gz \
    && tar -xzf ncbi-blast-2.16.0+-aarch64-linux.tar.gz \
    && mv ncbi-blast-2.16.0+ /opt/blast \
    && rm ncbi-blast-2.16.0+-aarch64-linux.tar.gz

# Download and install IGBLAST
RUN cd /tmp && \
    wget https://ftp.ncbi.nlm.nih.gov/blast/executables/igblast/release/1.22.0/ncbi-igblast-1.22.0-x64-linux.tar.gz -O igblast.tar.gz && \
    tar -xzf igblast.tar.gz && \
    mv ncbi-igblast-1.22.0 /opt/igblast && \
    rm igblast.tar.gz && \
    # Create symlinks for IGBLAST executables
    ln -sf /opt/igblast/bin/igblastn /usr/local/bin/igblastn && \
    ln -sf /opt/igblast/bin/makeblastdb /usr/local/bin/makeblastdb && \
    ln -sf /opt/igblast/bin/update_blastdb.pl /usr/local/bin/update_blastdb.pl

# Add BLAST and IGBLAST to PATH
ENV PATH="/opt/blast/bin:/opt/igblast/bin:/usr/local/bin:${PATH}"

# Install uv
RUN pip install uv

# Copy pyproject.toml first to leverage Docker cache
COPY pyproject.toml .
RUN uv sync

# Copy the rest of the application
COPY . .

# Create necessary directories
RUN mkdir -p instance/uploads instance/blast instance/igblast

# Set environment variables
ENV PYTHONPATH=/app
ENV BLASTDB=/app/app/database/blast
ENV GERMLINE=/app/app/database/germlines
ENV IGDATA=/app/app/database/igblast

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"] 