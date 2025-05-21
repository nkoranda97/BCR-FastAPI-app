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

1. Create enviornment and install dependencies
    ```bash
    uv sync
    ```

3. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

4. Run the application:
   ```bash
   uv run uvicorn app.main:app --reload
   # or 
   uv run startup.py
   ```


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
