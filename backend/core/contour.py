"""
Contour extraction module for geological map digitization.

This module provides the ContourExtractor class for extracting contour lines
from preprocessed geological maps using color-based detection and Hough
transform for line extraction.
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional
from shapely.geometry import LineString
import logging

logger = logging.getLogger(__name__)


class ContourExtractor:
    """
    Handles contour line extraction from geological maps.

    Contour lines in geological maps are typically brown/orange colored
    lines representing elevation. This class extracts these lines using
    color segmentation and line detection algorithms.
    """

    def __init__(self, color_range: Optional[Tuple] = None):
        """
        Initialize the ContourExtractor.

        Args:
            color_range: Optional tuple of (lower_brown, upper_brown) HSV ranges
        """
        # Default brown/orange color range for contours (HSV)
        # Brown: H(10-25), S(100-255), V(20-200)
        if color_range is None:
            self.lower_brown = np.array([10, 100, 20])
            self.upper_brown = np.array([25, 255, 200])
        else:
            self.lower_brown, self.upper_brown = color_range

        # Hough transform parameters
        self.hough_params = {
            'rho': 1,
            'theta': np.pi / 180,
            'threshold': 50,
            'minLineLength': 30,
            'maxLineGap': 10
        }

        logger.debug(f"ContourExtractor initialized with brown range: "
                    f"H({self.lower_brown[0]}-{self.upper_brown[0]}), "
                    f"S({self.lower_brown[1]}-{self.upper_brown[1]}), "
                    f"V({self.lower_brown[2]}-{self.upper_brown[2]})")

    def extract_color_mask(self, image: np.ndarray) -> np.ndarray:
        """
        Extract contour-colored regions from the image.

        Uses HSV color space to identify brown/orange regions typical
        of contour lines on geological maps.

        Args:
            image: Input BGR image

        Returns:
            Binary mask where white pixels indicate contour colors

        Raises:
            ValueError: If image is invalid
        """
        if image is None or image.size == 0:
            raise ValueError("Invalid input image")

        # Convert to HSV color space
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        # Create mask for brown/orange colors
        mask = cv2.inRange(hsv, self.lower_brown, self.upper_brown)

        # Apply morphological operations to clean the mask
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        logger.debug(f"Extracted color mask, found {np.sum(mask > 0)} contour pixels")
        return mask

    def detect_edges(self, mask: np.ndarray) -> np.ndarray:
        """
        Detect edges in the color mask.

        Args:
            mask: Binary mask from extract_color_mask

        Returns:
            Edge-detected image

        Raises:
            ValueError: If mask is invalid
        """
        if mask is None or mask.size == 0:
            raise ValueError("Invalid input mask")

        # Apply Canny edge detection
        edges = cv2.Canny(mask, 50, 150)

        logger.debug(f"Detected edges, found {np.sum(edges > 0)} edge pixels")
        return edges

    def extract_lines(self, edges: np.ndarray) -> List[np.ndarray]:
        """
        Extract lines from edge-detected image using probabilistic Hough transform.

        Args:
            edges: Edge-detected image

        Returns:
            List of line segments, each as a numpy array [[x1, y1, x2, y2]]

        Raises:
            ValueError: If edges is invalid
        """
        if edges is None or edges.size == 0:
            raise ValueError("Invalid edge image")

        # Apply HoughLinesP for probabilistic line detection
        lines = cv2.HoughLinesP(
            edges,
            rho=self.hough_params['rho'],
            theta=self.hough_params['theta'],
            threshold=self.hough_params['threshold'],
            minLineLength=self.hough_params['minLineLength'],
            maxLineGap=self.hough_params['maxLineGap']
        )

        if lines is None:
            logger.warning("No lines detected in edge image")
            return []

        # Convert numpy array to list of arrays for consistency
        lines_list = [line for line in lines]
        logger.debug(f"Extracted {len(lines_list)} line segments")
        return lines_list

    def lines_to_linestrings(
        self,
        lines: List[np.ndarray],
        scale: float = 1.0
    ) -> List[LineString]:
        """
        Convert detected lines to Shapely LineString objects.

        Args:
            lines: List of line segments from Hough transform
            scale: Scale factor to convert pixel coordinates to geographic units

        Returns:
            List of LineString geometries
        """
        linestrings = []

        for line in lines:
            x1, y1, x2, y2 = line[0]

            # Apply scale factor
            x1_scaled, y1_scaled = x1 / scale, y1 / scale
            x2_scaled, y2_scaled = x2 / scale, y2 / scale

            # Create LineString
            linestring = LineString([
                (x1_scaled, y1_scaled),
                (x2_scaled, y2_scaled)
            ])
            linestrings.append(linestring)

        logger.debug(f"Converted {len(linestrings)} lines to LineString objects")
        return linestrings

    def extract(
        self,
        image: np.ndarray,
        scale: float = 1.0,
        return_debug: bool = False
    ) -> Tuple[List[LineString], Optional[np.ndarray]]:
        """
        Complete contour extraction pipeline.

        Args:
            image: Input preprocessed BGR image
            scale: Scale factor for coordinate conversion
            return_debug: If True, also return the edge-detected image for debugging

        Returns:
            Tuple of (list of LineString contours, optional edge image)

        Raises:
            ValueError: If image is invalid
        """
        if image is None or image.size == 0:
            raise ValueError("Invalid input image")

        logger.info(f"Starting contour extraction for image: {image.shape}")

        # Step 1: Extract color regions
        mask = self.extract_color_mask(image)
        logger.debug("Step 1/4: Color mask extraction complete")

        # Step 2: Detect edges
        edges = self.detect_edges(mask)
        logger.debug("Step 2/4: Edge detection complete")

        # Step 3: Extract lines
        lines = self.extract_lines(edges)
        logger.debug("Step 3/4: Line extraction complete")

        # Step 4: Convert to LineString
        linestrings = self.lines_to_linestrings(lines, scale=scale)
        logger.debug("Step 4/4: LineString conversion complete")

        logger.info(f"Contour extraction complete: {len(linestrings)} contours found")

        if return_debug:
            return linestrings, edges
        else:
            return linestrings, None

    def set_color_range(
        self,
        lower_h: int, lower_s: int, lower_v: int,
        upper_h: int, upper_s: int, upper_v: int
    ) -> None:
        """
        Update the color range for contour detection.

        Args:
            lower_h: Lower bound for Hue (0-180)
            lower_s: Lower bound for Saturation (0-255)
            lower_v: Lower bound for Value (0-255)
            upper_h: Upper bound for Hue (0-180)
            upper_s: Upper bound for Saturation (0-255)
            upper_v: Upper bound for Value (0-255)
        """
        self.lower_brown = np.array([lower_h, lower_s, lower_v])
        self.upper_brown = np.array([upper_h, upper_s, upper_v])
        logger.debug(f"Updated color range to H({lower_h}-{upper_h}), "
                    f"S({lower_s}-{upper_s}), V({lower_v}-{upper_v})")

    def set_hough_params(
        self,
        rho: Optional[float] = None,
        theta: Optional[float] = None,
        threshold: Optional[int] = None,
        minLineLength: Optional[int] = None,
        maxLineGap: Optional[int] = None
    ) -> None:
        """
        Update Hough transform parameters.

        Args:
            rho: Distance resolution in pixels
            theta: Angle resolution in radians
            threshold: Minimum number of intersections to detect a line
            minLineLength: Minimum line length in pixels
            maxLineGap: Maximum gap between line segments to connect
        """
        if rho is not None:
            self.hough_params['rho'] = rho
        if theta is not None:
            self.hough_params['theta'] = theta
        if threshold is not None:
            self.hough_params['threshold'] = threshold
        if minLineLength is not None:
            self.hough_params['minLineLength'] = minLineLength
        if maxLineGap is not None:
            self.hough_params['maxLineGap'] = maxLineGap
        logger.debug(f"Updated Hough parameters: {self.hough_params}")
