"""
Tests for file upload API routes.
"""

import os
import pytest
from fastapi.testclient import TestClient
from io import BytesIO

from api.main import app
from models.task import Task, TaskStatus


# Create test client
client = TestClient(app)


@pytest.fixture
def sample_png():
    """Create a sample PNG file for testing."""
    # Create a minimal PNG file (1x1 pixel)
    png_data = (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
        b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01'
        b'\x00\x00\x05\x00\x01\x0d\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
    )
    return BytesIO(png_data)


@pytest.fixture
def sample_invalid_file():
    """Create an invalid file for testing."""
    return BytesIO(b'This is not a valid image or PDF file')


def test_upload_png(sample_png):
    """Test uploading a valid PNG file."""
    files = {"file": ("test.png", sample_png, "image/png")}
    response = client.post("/api/upload/image", files=files)

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert "id" in data
    assert "filename" in data
    assert data["filename"] == "test.png"
    assert data["status"] in ["pending", "PENDING"]
    assert "progress" in data
    assert data["progress"] == 0.0
    assert "created_at" in data
    assert "file_path" in data

    # Check that file was saved
    assert "uploads" in data["file_path"]
    assert "test" not in data["file_path"]  # Should use UUID, not original name


def test_upload_invalid_file(sample_invalid_file):
    """Test uploading an invalid file type."""
    files = {"file": ("test.txt", sample_invalid_file, "text/plain")}
    response = client.post("/api/upload/image", files=files)

    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "Invalid file type" in data["detail"] or "Invalid file extension" in data["detail"]


def test_upload_jpeg():
    """Test uploading a valid JPEG file."""
    # Create a minimal JPEG file
    jpeg_data = (
        b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
        b'\xff\xdb\x00C\x00\x03\x02\x02\x03\x02\x02\x03\x03\x03\x03\x04\x03\x03'
        b'\x04\x05\x08\x05\x05\x04\x04\x05\n\x07\x07\x06\x08\x0c\n\x0c\x0c\x0b'
        b'\n\x0b\x0b\r\x0e\x12\x10\r\x0e\x11\x0e\x0b\x0b\x10\x16\x10\x11\x13\x14'
        b'\x15\x15\x15\x0c\x0f\x17\x18\x16\x14\x18\x12\x14\x15\x14\xff\xc0\x00'
        b'\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x14\x00\x01\x00'
        b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\n\xff\xc4\x00'
        b'\x14\x10\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
        b'\x00\x00\xff\xda\x00\x08\x01\x01\x00\x00?\x00T\x9f\xff\xd9'
    )
    jpeg_file = BytesIO(jpeg_data)

    files = {"file": ("test.jpg", jpeg_file, "image/jpeg")}
    response = client.post("/api/upload/image", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == "test.jpg"
    assert "file_path" in data


def test_get_task_status(sample_png):
    """Test retrieving task status."""
    # First upload a file to get a task_id
    files = {"file": ("test.png", sample_png, "image/png")}
    upload_response = client.post("/api/upload/image", files=files)
    task_data = upload_response.json()
    task_id = task_data["id"]

    # Now get the task status
    response = client.get(f"/api/upload/task/{task_id}")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == task_id
    assert data["filename"] == "test.png"
    assert data["status"] in ["pending", "PENDING"]
    assert "progress" in data
    assert "created_at" in data


def test_get_nonexistent_task():
    """Test retrieving a non-existent task."""
    fake_task_id = "nonexistent-task-id"
    response = client.get(f"/api/upload/task/{fake_task_id}")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()


def test_upload_missing_file():
    """Test upload without providing a file."""
    response = client.post("/api/upload/image")

    assert response.status_code == 422  # Unprocessable Entity
