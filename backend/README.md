# Geological Map Digitizer - Backend

FastAPI-based backend service for geological map digitization using OCR and computer vision.

## Setup

1. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install GDAL** (if not already installed)
   - Windows: Download from [GISInternals](https://www.gisinternals.com/)
   - Mac: `brew install gdal`
   - Linux: `sudo apt-get install gdal-bin`

4. **Run development server**
   ```bash
   uvicorn api.main:app --reload --port 8000
   ```

## Project Structure

```
backend/
├── api/
│   ├── routes/          # API route handlers
│   └── main.py          # FastAPI application entry point
├── core/                # Core functionality (config, security)
├── models/              # Database models
├── utils/               # Utility functions
└── requirements.txt     # Python dependencies
```

## API Documentation

Once running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
