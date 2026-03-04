"""
Tests for the stratigraphy extraction module.

Tests the StratigraphyExtractor class for extracting stratigraphic units.
"""

import pytest
import cv2
import numpy as np
from core.stratigraphy import StratigraphyExtractor, SKLEARN_AVAILABLE


class TestExtractColors:
    """Test color extraction functionality."""

    @pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn not installed")
    def test_extract_colors_three_colors(self):
        """Test extracting three dominant colors."""
        extractor = StratigraphyExtractor(n_clusters=3)
        # Create image with 3 distinct color regions
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        image[:33, :] = [255, 0, 0]      # Red
        image[33:66, :] = [0, 255, 0]    # Green
        image[66:, :] = [0, 0, 255]      # Blue

        colors = extractor.extract_colors(image)

        assert colors.shape == (3, 3)
        assert colors.dtype == np.uint8

    @pytest.mark.skipif(not SKLEARN_AVAILABLE, reason="scikit-learn not installed")
    def test_extract_colors_invalid_image(self):
        """Test color extraction with invalid input."""
        extractor = StratigraphyExtractor()

        with pytest.raises(ValueError, match="Invalid input image"):
            extractor.extract_colors(None)


class TestCreateColorMasks:
    """Test color mask creation."""

    def test_create_color_masks_two_colors(self):
        """Test creating masks for two colors."""
        extractor = StratigraphyExtractor(n_clusters=2)
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        image[:50, :] = [100, 50, 50]

        colors = np.array([[100, 50, 50], [50, 50, 50]], dtype=np.uint8)
        masks = extractor.create_color_masks(image, colors)

        assert len(masks) == 2

    def test_create_color_masks_invalid_image(self):
        """Test mask creation with invalid input."""
        extractor = StratigraphyExtractor()
        colors = np.array([[100, 50, 50]])

        with pytest.raises(ValueError, match="Invalid input image"):
            extractor.create_color_masks(None, colors)


class TestFindContours:
    """Test contour finding functionality."""

    def test_find_contours_rectangle(self):
        """Test finding contours in rectangular mask."""
        extractor = StratigraphyExtractor()
        mask = np.zeros((100, 100), dtype=np.uint8)
        cv2.rectangle(mask, (10, 10), (90, 90), 255, -1)

        contours = extractor.find_contours(mask)

        assert isinstance(contours, list)
        assert len(contours) > 0

    def test_find_contours_empty(self):
        """Test finding contours in empty mask."""
        extractor = StratigraphyExtractor()
        mask = np.zeros((100, 100), dtype=np.uint8)

        contours = extractor.find_contours(mask)

        assert isinstance(contours, list)
        assert len(contours) == 0


class TestContoursToPolygons:
    """Test contour to polygon conversion."""

    def test_contours_to_polygons_basic(self):
        """Test basic contour conversion."""
        extractor = StratigraphyExtractor()
        # Create a simple rectangular contour
        contour = np.array([
            [[10, 10]],
            [[90, 10]],
            [[90, 90]],
            [[10, 90]]
        ], dtype=np.int32)

        polygons = extractor.contours_to_polygons([contour])

        assert len(polygons) > 0

    def test_contours_to_polygons_min_area_filter(self):
        """Test polygon filtering by minimum area."""
        extractor = StratigraphyExtractor(min_area=1000)
        # Create small contour
        small_contour = np.array([
            [[10, 10]],
            [[15, 10]],
            [[15, 15]],
            [[10, 15]]
        ], dtype=np.int32)

        polygons = extractor.contours_to_polygons([small_contour])

        # Small polygon should be filtered out
        assert len(polygons) == 0

    def test_contours_to_polygons_empty(self):
        """Test with empty contour list."""
        extractor = StratigraphyExtractor()
        polygons = extractor.contours_to_polygons([])

        assert len(polygons) == 0


class TestExtract:
    """Test complete extraction pipeline."""

    def test_extract_complete_pipeline(self):
        """Test the complete stratigraphy extraction."""
        extractor = StratigraphyExtractor(n_clusters=2)
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.rectangle(image, (10, 10), (90, 90), (200, 100, 50), -1)

        result = extractor.extract(image)

        assert isinstance(result, dict)

    def test_extract_invalid_image(self):
        """Test extraction with invalid input."""
        extractor = StratigraphyExtractor()

        with pytest.raises(ValueError, match="Invalid input image"):
            extractor.extract(None)


class TestParameterUpdates:
    """Test parameter update methods."""

    def test_set_n_clusters(self):
        """Test updating cluster count."""
        extractor = StratigraphyExtractor()
        extractor.set_n_clusters(10)

        assert extractor.n_clusters == 10

    def test_set_min_area(self):
        """Test updating minimum area."""
        extractor = StratigraphyExtractor()
        extractor.set_min_area(500)

        assert extractor.min_area == 500


class TestSklearnFallback:
    """Test scikit-learn fallback behavior."""

    @pytest.mark.skipif(SKLEARN_AVAILABLE, reason="scikit-learn is installed")
    def test_extract_colors_without_sklearn(self):
        """Test color extraction without scikit-learn raises error."""
        extractor = StratigraphyExtractor()
        image = np.zeros((100, 100, 3), dtype=np.uint8)

        with pytest.raises(ValueError, match="scikit-learn is required"):
            extractor.extract_colors(image)

    @pytest.mark.skipif(SKLEARN_AVAILABLE, reason="scikit-learn is installed")
    def test_extract_uses_predefined_colors(self):
        """Test extraction uses predefined colors when sklearn unavailable."""
        extractor = StratigraphyExtractor()
        image = np.ones((100, 100, 3), dtype=np.uint8) * 100

        result = extractor.extract(image)

        # Should use predefined colors and return results
        assert isinstance(result, dict)
