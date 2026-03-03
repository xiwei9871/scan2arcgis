"""
FastAPI application for the Geological Map Digitizer.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes.upload import router as upload_router

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

# Include routers
app.include_router(upload_router)


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
