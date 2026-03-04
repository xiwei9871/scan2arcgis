"""
Tests for the contour extraction module.

Tests the ContourExtractor class for extracting contour lines
from geological maps.
"""

import pytest
import cv2
import numpy as np
from core.contour import ContourExtractor


class TestExtractColorMask:
    """Test color mask extraction."""

    def test_extract_color_mask_with_brown_region(self):
        """Test mask extraction with brown region."""
        extractor = ContourExtractor()
        # Create test image with brown region
        # First create image in HSV with proper brown color, then convert to BGR
        hsv_image = np.zeros((100, 100, 3), dtype=np.uint8)
        hsv_image[30:70, 30:70] = [18, 200, 100]  # Brown in HSV
        image = cv2.cvtColor(hsv_image, cv2.COLOR_HSV2BGR)

        mask = extractor.extract_color_mask(image)

        assert mask.shape[:2] == (100, 100)
        # Should detect brown region
        assert np.sum(mask > 0) > 0

    def test_extract_color_mask_no_brown(self):
        """Test mask extraction without brown colors."""
        extractor = ContourExtractor()
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        image[:, :] = [255, 0, 0]  # Blue only

        mask = extractor.extract_color_mask(image)

        assert mask.shape[:2] == (100, 100)
        # Should not detect any brown
        assert np.sum(mask > 0) == 0

    def test_extract_color_mask_invalid_image(self):
        """Test mask extraction with invalid input."""
        extractor = ContourExtractor()

        with pytest.raises(ValueError, match="Invalid input image"):
            extractor.extract_color_mask(None)


class TestDetectEdges:
    """Test edge detection."""

    def test_detect_edges_with_rectangle(self):
        """Test edge detection on rectangular region."""
        extractor = ContourExtractor()
        mask = np.zeros((100, 100), dtype=np.uint8)
        cv2.rectangle(mask, (30, 30), (70, 70), 255, 2)

        edges = extractor.detect_edges(mask)

        assert edges.shape == (100, 100)
        assert np.sum(edges > 0) > 0

    def test_detect_edges_empty_mask(self):
        """Test edge detection on empty mask."""
        extractor = ContourExtractor()
        mask = np.zeros((100, 100), dtype=np.uint8)

        edges = extractor.detect_edges(mask)

        assert edges.shape == (100, 100)
        assert np.sum(edges > 0) == 0

    def test_detect_edges_invalid_mask(self):
        """Test edge detection with invalid input."""
        extractor = ContourExtractor()

        with pytest.raises(ValueError, match="Invalid edge image"):
            extractor.extract_lines(None)


class TestExtractLines:
    """Test line extraction."""

    def test_extract_lines_with_horizontal_line(self):
        """Test line extraction on horizontal line."""
        extractor = ContourExtractor()
        edges = np.zeros((100, 100), dtype=np.uint8)
        cv2.line(edges, (10, 50), (90, 50), 255, 2)

        lines = extractor.extract_lines(edges)

        assert isinstance(lines, list)
        # Should detect at least one line
        assert len(lines) > 0

    def test_extract_lines_no_lines(self):
        """Test line extraction on empty image."""
        extractor = ContourExtractor()
        edges = np.zeros((100, 100), dtype=np.uint8)

        lines = extractor.extract_lines(edges)

        assert isinstance(lines, list)
        assert len(lines) == 0

    def test_extract_lines_invalid_edges(self):
        """Test line extraction with invalid input."""
        extractor = ContourExtractor()

        with pytest.raises(ValueError, match="Invalid edge image"):
            extractor.extract_lines(None)


class TestLinesToLinestrings:
    """Test conversion to LineString objects."""

    def test_lines_to_linestrings_basic(self):
        """Test basic line to LineString conversion."""
        extractor = ContourExtractor()
        # Create mock line data
        lines = [
            np.array([[10, 10, 50, 50]]),
            np.array([[20, 20, 60, 60]])
        ]

        linestrings = extractor.lines_to_linestrings(lines)

        assert len(linestrings) == 2
        # Check first linestring
        assert linestrings[0].coords[0] == (10.0, 10.0)
        assert linestrings[0].coords[1] == (50.0, 50.0)

    def test_lines_to_linestrings_with_scale(self):
        """Test line conversion with scale factor."""
        extractor = ContourExtractor()
        lines = [np.array([[100, 100, 200, 200]])]

        linestrings = extractor.lines_to_linestrings(lines, scale=2.0)

        assert len(linestrings) == 1
        # Coordinates should be halved due to scale
        assert linestrings[0].coords[0] == (50.0, 50.0)
        assert linestrings[0].coords[1] == (100.0, 100.0)

    def test_lines_to_linestrings_empty(self):
        """Test line conversion with empty list."""
        extractor = ContourExtractor()
        linestrings = extractor.lines_to_linestrings([])

        assert len(linestrings) == 0


class TestExtract:
    """Test complete extraction pipeline."""

    def test_extract_complete_pipeline(self):
        """Test the complete contour extraction pipeline."""
        extractor = ContourExtractor()
        # Create test image with brown line
        image = np.ones((100, 100, 3), dtype=np.uint8) * 255
        # Draw brown line (BGR: 20, 150, 100)
        cv2.line(image, (10, 50), (90, 50), (20, 150, 100), 3)

        contours, _ = extractor.extract(image)

        assert isinstance(contours, list)

    def test_extract_with_debug_image(self):
        """Test extraction with debug image return."""
        extractor = ContourExtractor()
        image = np.ones((100, 100, 3), dtype=np.uint8) * 255
        cv2.line(image, (10, 50), (90, 50), (20, 150, 100), 3)

        contours, edges = extractor.extract(image, return_debug=True)

        assert isinstance(contours, list)
        assert edges is not None
        assert edges.shape == (100, 100)

    def test_extract_invalid_image(self):
        """Test extraction with invalid input."""
        extractor = ContourExtractor()

        with pytest.raises(ValueError, match="Invalid input image"):
            extractor.extract(None)


class TestParameterUpdates:
    """Test parameter update methods."""

    def test_set_color_range(self):
        """Test updating color range."""
        extractor = ContourExtractor()

        extractor.set_color_range(
            lower_h=5, lower_s=80, lower_v=10,
            upper_h=30, upper_s=255, upper_v=220
        )

        assert extractor.lower_brown[0] == 5
        assert extractor.upper_brown[0] == 30

    def test_set_hough_params(self):
        """Test updating Hough parameters."""
        extractor = ContourExtractor()

        extractor.set_hough_params(threshold=100, minLineLength=50)

        assert extractor.hough_params['threshold'] == 100
        assert extractor.hough_params['minLineLength'] == 50

    def test_set_partial_hough_params(self):
        """Test updating only some Hough parameters."""
        extractor = ContourExtractor()

        original_theta = extractor.hough_params['theta']
        extractor.set_hough_params(threshold=75)

        assert extractor.hough_params['threshold'] == 75
        assert extractor.hough_params['theta'] == original_theta  # Unchanged
