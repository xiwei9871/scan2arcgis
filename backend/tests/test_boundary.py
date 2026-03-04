"""
Tests for the geological boundary extraction module.

Tests the BoundaryExtractor class for extracting geological boundaries.
"""

import pytest
import cv2
import numpy as np
from shapely.geometry import LineString
from core.boundary import BoundaryExtractor


class TestDetectColorEdges:
    """Test edge detection functionality."""

    def test_detect_color_edges_with_rectangle(self):
        """Test edge detection on rectangular region."""
        extractor = BoundaryExtractor()
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.rectangle(image, (30, 30), (70, 70), (255, 255, 255), 2)

        edges = extractor.detect_color_edges(image)

        assert edges.shape == (100, 100)
        assert np.sum(edges > 0) > 0

    def test_detect_color_edges_uniform(self):
        """Test edge detection on uniform image."""
        extractor = BoundaryExtractor()
        image = np.ones((100, 100, 3), dtype=np.uint8) * 128

        edges = extractor.detect_color_edges(image)

        assert edges.shape == (100, 100)
        # Uniform image should have minimal edges
        assert np.sum(edges > 0) < 100  # Allow some noise

    def test_detect_color_edges_invalid_image(self):
        """Test edge detection with invalid input."""
        extractor = BoundaryExtractor()

        with pytest.raises(ValueError, match="Invalid input image"):
            extractor.detect_color_edges(None)


class TestExtractLines:
    """Test line extraction functionality."""

    def test_extract_lines_horizontal_line(self):
        """Test line extraction on horizontal line."""
        extractor = BoundaryExtractor()
        edges = np.zeros((100, 100), dtype=np.uint8)
        cv2.line(edges, (10, 50), (90, 50), 255, 2)

        lines = extractor.extract_lines(edges)

        assert isinstance(lines, list)
        assert len(lines) > 0

    def test_extract_lines_diagonal_line(self):
        """Test line extraction on diagonal line."""
        extractor = BoundaryExtractor()
        edges = np.zeros((100, 100), dtype=np.uint8)
        cv2.line(edges, (10, 10), (90, 90), 255, 2)

        lines = extractor.extract_lines(edges)

        assert isinstance(lines, list)
        assert len(lines) > 0

    def test_extract_lines_no_lines(self):
        """Test line extraction on empty image."""
        extractor = BoundaryExtractor()
        edges = np.zeros((100, 100), dtype=np.uint8)

        lines = extractor.extract_lines(edges)

        assert isinstance(lines, list)
        assert len(lines) == 0

    def test_extract_lines_invalid_edges(self):
        """Test line extraction with invalid input."""
        extractor = BoundaryExtractor()

        with pytest.raises(ValueError, match="Invalid edge image"):
            extractor.extract_lines(None)


class TestConnectLines:
    """Test line connection functionality."""

    def test_connect_lines_basic(self):
        """Test basic line connection."""
        extractor = BoundaryExtractor()
        lines = [
            np.array([[10, 10, 50, 50]]),
            np.array([[20, 20, 60, 60]])
        ]

        boundaries = extractor.connect_lines(lines)

        assert len(boundaries) == 2
        assert all(isinstance(b, LineString) for b in boundaries)

    def test_connect_lines_empty(self):
        """Test line connection with empty list."""
        extractor = BoundaryExtractor()
        boundaries = extractor.connect_lines([])

        assert len(boundaries) == 0

    def test_connect_lines_single_segment(self):
        """Test line connection with single segment."""
        extractor = BoundaryExtractor()
        lines = [np.array([[10, 10, 90, 10]])]

        boundaries = extractor.connect_lines(lines)

        assert len(boundaries) == 1
        assert boundaries[0].coords[0] == (10, 10)
        assert boundaries[0].coords[1] == (90, 10)


class TestExtract:
    """Test complete extraction pipeline."""

    def test_extract_complete_pipeline(self):
        """Test the complete boundary extraction pipeline."""
        extractor = BoundaryExtractor()
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.line(image, (10, 50), (90, 50), (255, 255, 255), 2)

        boundaries, _ = extractor.extract(image)

        assert isinstance(boundaries, list)

    def test_extract_with_debug_image(self):
        """Test extraction with debug image return."""
        extractor = BoundaryExtractor()
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.line(image, (10, 50), (90, 50), (255, 255, 255), 2)

        boundaries, edges = extractor.extract(image, return_debug=True)

        assert isinstance(boundaries, list)
        assert edges is not None
        assert edges.shape == (100, 100)

    def test_extract_invalid_image(self):
        """Test extraction with invalid input."""
        extractor = BoundaryExtractor()

        with pytest.raises(ValueError, match="Invalid input image"):
            extractor.extract(None)


class TestParameterUpdates:
    """Test parameter update methods."""

    def test_set_canny_params(self):
        """Test updating Canny parameters."""
        extractor = BoundaryExtractor()

        extractor.set_canny_params(threshold1=75, threshold2=200)

        assert extractor.canny_params['threshold1'] == 75
        assert extractor.canny_params['threshold2'] == 200

    def test_set_hough_params(self):
        """Test updating Hough parameters."""
        extractor = BoundaryExtractor()

        extractor.set_hough_params(threshold=50, minLineLength=30)

        assert extractor.hough_params['threshold'] == 50
        assert extractor.hough_params['minLineLength'] == 30

    def test_set_partial_params(self):
        """Test updating only some parameters."""
        extractor = BoundaryExtractor()

        original_threshold1 = extractor.canny_params['threshold1']
        extractor.set_canny_params(threshold2=180)

        assert extractor.canny_params['threshold1'] == original_threshold1  # Unchanged
        assert extractor.canny_params['threshold2'] == 180
