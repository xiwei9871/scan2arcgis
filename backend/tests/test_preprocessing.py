"""
Tests for the image preprocessing module.

Tests the ImagePreprocessor class for various preprocessing operations.
"""

import pytest
import cv2
import numpy as np
from core.preprocessing import ImagePreprocessor


class TestDenoise:
    """Test denoising functionality."""

    def test_denoise_random_image(self):
        """Test denoising on a random test image."""
        preprocessor = ImagePreprocessor()
        # Create a noisy test image
        image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)

        result = preprocessor.denoise(image)

        assert result.shape == image.shape
        assert result.dtype == np.uint8

    def test_denoise_smooth_image(self):
        """Test denoising on a smooth image."""
        preprocessor = ImagePreprocessor()
        # Create a smooth image
        image = np.ones((100, 100, 3), dtype=np.uint8) * 128

        result = preprocessor.denoise(image)

        assert result.shape == image.shape
        assert result.dtype == np.uint8

    def test_denoise_invalid_image(self):
        """Test denoising with invalid input."""
        preprocessor = ImagePreprocessor()

        with pytest.raises(ValueError, match="Invalid input image"):
            preprocessor.denoise(None)

        with pytest.raises(ValueError, match="Invalid input image"):
            preprocessor.denoise(np.array([]))


class TestEnhanceContrast:
    """Test contrast enhancement functionality."""

    def test_enhance_contrast_uniform(self):
        """Test contrast enhancement on uniform image."""
        preprocessor = ImagePreprocessor()
        image = np.ones((100, 100, 3), dtype=np.uint8) * 100

        result = preprocessor.enhance_contrast(image)

        assert result.shape == image.shape

    def test_enhance_contrast_gradient(self):
        """Test contrast enhancement on gradient image."""
        preprocessor = ImagePreprocessor()
        # Create a gradient image
        image = np.linspace(0, 255, 100, dtype=np.uint8)
        image = np.tile(image[:, np.newaxis], (1, 100, 3))

        result = preprocessor.enhance_contrast(image)

        assert result.shape == image.shape

    def test_enhance_contrast_invalid_image(self):
        """Test contrast enhancement with invalid input."""
        preprocessor = ImagePreprocessor()

        with pytest.raises(ValueError, match="Invalid input image"):
            preprocessor.enhance_contrast(None)


class TestBinarize:
    """Test binarization functionality."""

    def test_binarize_color_image(self):
        """Test binarization of color image."""
        preprocessor = ImagePreprocessor()
        image = np.ones((100, 100, 3), dtype=np.uint8) * 100

        result = preprocessor.binarize(image)

        assert len(result.shape) == 2  # Binary image is single channel
        assert result.shape == (100, 100)

    def test_binarize_grayscale_image(self):
        """Test binarization of grayscale image."""
        preprocessor = ImagePreprocessor()
        image = np.ones((100, 100), dtype=np.uint8) * 100

        result = preprocessor.binarize(image)

        assert len(result.shape) == 2
        assert result.shape == (100, 100)

    def test_binarize_custom_threshold(self):
        """Test binarization with custom threshold."""
        preprocessor = ImagePreprocessor()
        image = np.ones((100, 100, 3), dtype=np.uint8) * 200

        result_low = preprocessor.binarize(image, threshold=150)
        result_high = preprocessor.binarize(image, threshold=250)

        # With lower threshold, more pixels should be white (255)
        assert np.sum(result_low) >= np.sum(result_high)

    def test_binarize_invalid_image(self):
        """Test binarization with invalid input."""
        preprocessor = ImagePreprocessor()

        with pytest.raises(ValueError, match="Invalid input image"):
            preprocessor.binarize(None)


class TestRemoveBackground:
    """Test background removal functionality."""

    def test_remove_background_white(self):
        """Test removing white background."""
        preprocessor = ImagePreprocessor()
        # Create image with white background
        image = np.ones((100, 100, 3), dtype=np.uint8) * 255
        image[30:70, 30:70] = [100, 50, 50]  # Add colored region

        result = preprocessor.remove_background(image)

        assert result.shape == image.shape
        # White background should be removed (black)
        # Colored region should remain

    def test_remove_background_no_white(self):
        """Test background removal on image without white."""
        preprocessor = ImagePreprocessor()
        image = np.ones((100, 100, 3), dtype=np.uint8) * 100

        result = preprocessor.remove_background(image)

        assert result.shape == image.shape

    def test_remove_background_invalid_image(self):
        """Test background removal with invalid input."""
        preprocessor = ImagePreprocessor()

        with pytest.raises(ValueError, match="Invalid input image"):
            preprocessor.remove_background(None)


class TestPreprocess:
    """Test complete preprocessing pipeline."""

    def test_preprocess_complete_pipeline(self):
        """Test the complete preprocessing pipeline."""
        preprocessor = ImagePreprocessor()
        # Create a test image
        image = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)

        result = preprocessor.preprocess(image)

        assert result.shape == image.shape
        assert result.dtype == np.uint8

    def test_preprocess_invalid_image(self):
        """Test preprocessing with invalid input."""
        preprocessor = ImagePreprocessor()

        with pytest.raises(ValueError, match="Invalid input image"):
            preprocessor.preprocess(None)

    def test_preprocess_white_background(self):
        """Test preprocessing on image with white background."""
        preprocessor = ImagePreprocessor()
        # Create image with white background and colored regions
        image = np.ones((100, 100, 3), dtype=np.uint8) * 255
        image[20:40, 20:40] = [150, 100, 50]
        image[60:80, 60:80] = [50, 100, 150]

        result = preprocessor.preprocess(image)

        assert result.shape == image.shape


class TestParameterUpdates:
    """Test parameter update methods."""

    def test_set_denoise_params(self):
        """Test updating denoising parameters."""
        preprocessor = ImagePreprocessor()

        preprocessor.set_denoise_params(h=15, hColor=15)

        assert preprocessor.denoise_params['h'] == 15
        assert preprocessor.denoise_params['hColor'] == 15

    def test_set_clahe_params(self):
        """Test updating CLAHE parameters."""
        preprocessor = ImagePreprocessor()

        preprocessor.set_clahe_params(clipLimit=5.0, tileGridSize=(4, 4))

        assert preprocessor.clahe_params['clipLimit'] == 5.0
        assert preprocessor.clahe_params['tileGridSize'] == (4, 4)

    def test_set_partial_params(self):
        """Test updating only some parameters."""
        preprocessor = ImagePreprocessor()

        original_h = preprocessor.denoise_params['h']
        preprocessor.set_denoise_params(h=20)

        assert preprocessor.denoise_params['h'] == 20
        assert preprocessor.denoise_params['hColor'] == original_h  # Unchanged
