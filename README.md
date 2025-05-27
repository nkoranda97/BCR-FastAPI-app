# BCR FastAPI

A FastAPI-based application for BCR Sequence Analysis.

## Project Structure

```
bcr_fastAPI/
├── app/                    # Main application package
│   ├── core/              # Core application components
│   ├── database/          # Database models and migrations
│   ├── routers/           # API route handlers
│   ├── schemas/           # Pydantic models/schemas
│   ├── services/          # Utilities
│   ├── static/            # Static files (CSS, JS, images)
│   └── templates/         # HTML templates
├── instance/              # Instance-specific files
├── test_input/           # Test input files
└── notebooks/            # Jupyter notebooks for development
```

## Setup

1. Install Homebrew if not already installed:
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. Install required bioinformatics tools:
   - BLAST: 
     ```bash
     # macOS (Intel/Apple Silicon)
     brew install blast
     ```
   - IgBLAST:
     ```bash
     # macOS (Intel/Apple Silicon)
     # Download from NCBI
     wget https://ftp.ncbi.nlm.nih.gov/blast/executables/igblast/release/1.22.0/ncbi-igblast-1.22.0-x64-macosx.tar.gz
     
     # Extract and add to PATH
     tar -xzf ncbi-igblast-1.22.0-x64-macosx.tar.gz
     # Add to PATH in your .zshrc or .bash_profile
     export PATH=$PATH:/path/to/ncbi-igblast-1.22.0/bin
     ```
     Note: For Apple Silicon Macs, the x64 version requires Rosetta 2.
   - MUSCLE:
     ```bash
     # macOS (Intel/Apple Silicon)
     brew install muscle
     ```

3. Create enviornment and install dependencies
    ```bash
    uv sync
    ```

4. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. Run the application:
   ```bash
   uv run uvicorn app.main:app --reload
   # or 
   uv run startup.py
   ```

## Docker Setup

1. Install Docker:
   - For macOS: Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop)
   - For Linux: Follow the [Docker installation guide](https://docs.docker.com/engine/install/)
   - For Windows: Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop)

2. Pull and run the container:
   ```bash
   # Pull the image
   docker pull nkoranda/bcr-app:bcr-app

   # Run the container
   docker run -p 8000:8000 nkoranda/bcr-app:bcr-app
   ```

The application will be available at:
- http://127.0.0.1:8000 (localhost)
- http://0.0.0.0:8000 (accessible from other devices on the network)

## Local Development Server

The application will be available at:
- http://127.0.0.1:8000 (localhost)
- http://0.0.0.0:8000 (accessible from other devices on the network)

## Development

- The application uses FastAPI for the backend
- Database migrations are handled through Alembic
- Static files and templates are served through FastAPI's built-in static file handling

## Testing
(No testing yet lol)

Run tests using pytest:
```bash
pytest
```

## License

[Add your license information here]
