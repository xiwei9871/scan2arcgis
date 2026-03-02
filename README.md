# Geological Map Digitizer

An intelligent web-based tool for digitizing geological maps using OCR and computer vision technologies.

## Project Overview

This application automates the extraction of geological information from scanned maps, including:
- Text recognition using PaddleOCR
- Symbol and pattern recognition
- Interactive annotation and editing
- Export to multiple formats (GeoJSON, Shapefile, KML)

## Technology Stack

### Backend
- **Framework**: FastAPI 0.104.1
- **Computer Vision**: OpenCV, GDAL, Rasterio
- **OCR**: PaddleOCR
- **Geospatial**: GeoPandas, Shapely
- **Task Queue**: Celery + Redis
- **Testing**: Pytest

### Frontend
- **Framework**: React 18 with TypeScript
- **Canvas Library**: Fabric.js
- **UI Components**: Ant Design
- **State Management**: Zustand
- **Build Tool**: Vite

## Project Structure

```
.
├── backend/                 # FastAPI backend
│   ├── api/
│   │   └── routes/         # API endpoints
│   ├── core/               # Core configuration
│   ├── models/             # Data models
│   ├── utils/              # Utilities
│   └── requirements.txt    # Python dependencies
│
├── frontend/               # React frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── pages/          # Page components
│   │   ├── services/       # API services
│   │   └── types/          # TypeScript types
│   ├── package.json        # Node dependencies
│   └── tsconfig.json       # TypeScript config
│
└── README.md              # This file
```

## Getting Started

### Backend Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

## API Documentation

Once the backend is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## License

MIT
