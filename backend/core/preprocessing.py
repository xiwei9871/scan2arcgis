"""
Image preprocessing module for geological map digitization.

This module provides the ImagePreprocessor class for preparing scanned
geological maps for feature extraction through denoising, contrast
enhancement, and background removal.
"""

import cv2
import numpy as np
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """
    Handles image preprocessing operations for geological maps.

    Provides methods for denoising, contrast enhancement, binarization,
    and background removal to prepare images for feature extraction.
    """

    def __init__(self):
        """Initialize the ImagePreprocessor."""
        self.denoise_params = {
            'h': 10,
            'hColor': 10,
            'templateWindowSize': 7,
            'searchWindowSize': 21
        }
        self.clahe_params = {
            'clipLimit': 3.0,
            'tileGridSize': (8, 8)
        }

    def denoise(self, image: np.ndarray) -> np.ndarray:
        """
        Remove noise from the image using fast non-local means denoising.

        Args:
            image: Input BGR image

        Returns:
            Denoised image

        Raises:
            ValueError: If image is invalid
        """
        if image is None or image.size == 0:
            raise ValueError("Invalid input image")

        # Apply fast non-local means denoising for color images
        denoised = cv2.fastNlMeansDenoisingColored(
            image,
            None,
            self.denoise_params['h'],
            self.denoise_params['hColor'],
            self.denoise_params['templateWindowSize'],
            self.denoise_params['searchWindowSize']
        )

        logger.debug(f"Denoised image: {image.shape} -> {denoised.shape}")
        return denoised

    def enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """
        Enhance image contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization).

        Args:
            image: Input BGR image

        Returns:
            Contrast-enhanced image

        Raises:
            ValueError: If image is invalid
        """
        if image is None or image.size == 0:
            raise ValueError("Invalid input image")

        # Convert to LAB color space
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)

        # Apply CLAHE to L channel
        clahe = cv2.createCLAHE(
            clipLimit=self.clahe_params['clipLimit'],
            tileGridSize=self.clahe_params['tileGridSize']
        )
        l = clahe.apply(l)

        # Merge channels and convert back to BGR
        enhanced = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2BGR)

        logger.debug("Enhanced image contrast using CLAHE")
        return enhanced

    def binarize(self, image: np.ndarray, threshold: int = 127) -> np.ndarray:
        """
        Convert image to binary (black and white).

        Args:
            image: Input grayscale or BGR image
            threshold: Threshold value for binarization (0-255)

        Returns:
            Binary image (single channel)

        Raises:
            ValueError: If image is invalid
        """
        if image is None or image.size == 0:
            raise ValueError("Invalid input image")

        # Convert to grayscale if needed
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Apply threshold
        _, binary = cv2.threshold(gray, threshold, 255, cv2.THRESH_BINARY)

        logger.debug(f"Binarized image with threshold={threshold}")
        return binary

    def remove_background(self, image: np.ndarray) -> np.ndarray:
        """
        Remove white background from the image.

        Args:
            image: Input BGR image

        Returns:
            Image with white background removed

        Raises:
            ValueError: If image is invalid
        """
        if image is None or image.size == 0:
            raise ValueError("Invalid input image")

        # Convert to HSV color space
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        # Define white color range in HSV
        # White: low saturation, high value
        lower_white = np.array([0, 0, 200])
        upper_white = np.array([180, 30, 255])

        # Create mask for white pixels
        mask = cv2.inRange(hsv, lower_white, upper_white)

        # Invert mask to keep non-white pixels
        result = cv2.bitwise_and(image, image, mask=cv2.bitwise_not(mask))

        logger.debug("Removed white background from image")
        return result

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """
        Apply the complete preprocessing pipeline.

        This method applies denoising, contrast enhancement, and
        background removal in sequence to prepare the image for
        feature extraction.

        Args:
            image: Input BGR image

        Returns:
            Preprocessed image

        Raises:
            ValueError: If image is invalid
        """
        if image is None or image.size == 0:
            raise ValueError("Invalid input image")

        logger.info(f"Starting preprocessing pipeline for image: {image.shape}")

        # Step 1: Denoise
        processed = self.denoise(image)
        logger.debug("Step 1/3: Denoising complete")

        # Step 2: Enhance contrast
        processed = self.enhance_contrast(processed)
        logger.debug("Step 2/3: Contrast enhancement complete")

        # Step 3: Remove background
        processed = self.remove_background(processed)
        logger.debug("Step 3/3: Background removal complete")

        logger.info("Preprocessing pipeline complete")
        return processed

    def set_denoise_params(self, h: Optional[int] = None, hColor: Optional[int] = None,
                          templateWindowSize: Optional[int] = None,
                          searchWindowSize: Optional[int] = None) -> None:
        """
        Update denoising parameters.

        Args:
            h: Filter strength (higher=more denoising)
            hColor: Same as h for color components
            templateWindowSize: Size of template patch (odd, recommended 7)
            searchWindowSize: Size of search area (odd, recommended 21)
        """
        if h is not None:
            self.denoise_params['h'] = h
        if hColor is not None:
            self.denoise_params['hColor'] = hColor
        if templateWindowSize is not None:
            self.denoise_params['templateWindowSize'] = templateWindowSize
        if searchWindowSize is not None:
            self.denoise_params['searchWindowSize'] = searchWindowSize

    def set_clahe_params(self, clipLimit: Optional[float] = None,
                         tileGridSize: Optional[Tuple[int, int]] = None) -> None:
        """
        Update CLAHE parameters.

        Args:
            clipLimit: Threshold for contrast limiting (higher=more contrast)
            tileGridSize: Size of grid for histogram equalization
        """
        if clipLimit is not None:
            self.clahe_params['clipLimit'] = clipLimit
        if tileGridSize is not None:
            self.clahe_params['tileGridSize'] = tileGridSize
