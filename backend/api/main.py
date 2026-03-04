"""
FastAPI application for the Geological Map Digitizer.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api.routes.upload import router as upload_router
from api.routes.registration import router as registration_router
from api import websocket
import os

# Create FastAPI application
app = FastAPI(
    title="Geological Map Digitizer API",
    description="Backend API for digitizing and analyzing geological maps",
    version="0.1.0"
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Vite dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for uploaded images
uploads_dir = "uploads"
if not os.path.exists(uploads_dir):
    os.makedirs(uploads_dir)
app.mount("/api/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# Include routers
app.include_router(upload_router)
app.include_router(registration_router)
app.include_router(websocket.router)


@app.get("/")
async def root():
    """Root endpoint returning API information."""
    return {
        "message": "Geological Map Digitizer API",
        "version": "0.1.0"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
