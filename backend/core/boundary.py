"""
Geological boundary extraction module for digitizing geological maps.

This module provides the BoundaryExtractor class for extracting geological
boundaries (contact lines between different geological units) from maps.
"""

import cv2
import numpy as np
from typing import List, Tuple, Optional
from shapely.geometry import LineString
import logging

logger = logging.getLogger(__name__)


class BoundaryExtractor:
    """
    Handles geological boundary line extraction.

    Extracts contact lines between different geological units using
    edge detection and line fitting algorithms.
    """

    def __init__(self):
        """Initialize the BoundaryExtractor."""
        # Canny edge detection parameters
        self.canny_params = {
            'threshold1': 50,
            'threshold2': 150
        }

        # Hough transform parameters for line detection
        self.hough_params = {
            'rho': 1,
            'theta': np.pi / 180,
            'threshold': 30,  # Lower threshold for boundaries
            'minLineLength': 20,
            'maxLineGap': 5
        }

        logger.debug("BoundaryExtractor initialized")

    def detect_color_edges(self, image: np.ndarray) -> np.ndarray:
        """
        Detect edges using color boundary detection.

        Converts to grayscale and applies Canny edge detection.

        Args:
            image: Input BGR image

        Returns:
            Edge-detected image

        Raises:
            ValueError: If image is invalid
        """
        if image is None or image.size == 0:
            raise ValueError("Invalid input image")

        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply Canny edge detection
        edges = cv2.Canny(
            gray,
            self.canny_params['threshold1'],
            self.canny_params['threshold2']
        )

        logger.debug(f"Detected edges, found {np.sum(edges > 0)} edge pixels")
        return edges

    def extract_lines(self, edges: np.ndarray) -> List[np.ndarray]:
        """
        Extract line segments from edge-detected image.

        Uses probabilistic Hough transform to detect line segments.

        Args:
            edges: Edge-detected image

        Returns:
            List of line segments

        Raises:
            ValueError: If edges is invalid
        """
        if edges is None or edges.size == 0:
            raise ValueError("Invalid edge image")

        # Apply HoughLinesP for line detection
        lines = cv2.HoughLinesP(
            edges,
            rho=self.hough_params['rho'],
            theta=self.hough_params['theta'],
            threshold=self.hough_params['threshold'],
            minLineLength=self.hough_params['minLineLength'],
            maxLineGap=self.hough_params['maxLineGap']
        )

        if lines is None:
            logger.debug("No lines detected in edge image")
            return []

        # Convert numpy array to list
        lines_list = [line for line in lines]
        logger.debug(f"Extracted {len(lines_list)} boundary line segments")
        return lines_list

    def connect_lines(
        self,
        lines: List[np.ndarray],
        max_gap: float = 20
    ) -> List[LineString]:
        """
        Connect broken line segments into continuous boundaries.

        This is a simplified implementation that returns individual line
        segments as LineString objects. A more sophisticated version
        would connect nearby line endpoints.

        Args:
            lines: List of line segments
            max_gap: Maximum gap to connect lines (unused in current implementation)

        Returns:
            List of LineString geometries
        """
        linestrings = []

        for line in lines:
            x1, y1, x2, y2 = line[0]
            linestrings.append(LineString([(x1, y1), (x2, y2)]))

        logger.debug(f"Created {len(linestrings)} LineString objects")
        return linestrings

    def extract(
        self,
        image: np.ndarray,
        return_debug: bool = False
    ) -> Tuple[List[LineString], Optional[np.ndarray]]:
        """
        Complete boundary extraction pipeline.

        Args:
            image: Input preprocessed BGR image
            return_debug: If True, also return edge-detected image

        Returns:
            Tuple of (list of LineString boundaries, optional edge image)

        Raises:
            ValueError: If image is invalid
        """
        if image is None or image.size == 0:
            raise ValueError("Invalid input image")

        logger.info(f"Starting boundary extraction for image: {image.shape}")

        # Step 1: Detect edges
        edges = self.detect_color_edges(image)
        logger.debug("Step 1/2: Edge detection complete")

        # Step 2: Extract lines
        lines = self.extract_lines(edges)
        logger.debug("Step 2/2: Line extraction complete")

        # Step 3: Convert to LineString
        boundaries = self.connect_lines(lines)
        logger.info(f"Boundary extraction complete: {len(boundaries)} boundaries found")

        if return_debug:
            return boundaries, edges
        else:
            return boundaries, None

    def set_canny_params(
        self,
        threshold1: Optional[int] = None,
        threshold2: Optional[int] = None
    ) -> None:
        """
        Update Canny edge detection parameters.

        Args:
            threshold1: First threshold for edge detection
            threshold2: Second threshold for edge detection
        """
        if threshold1 is not None:
            self.canny_params['threshold1'] = threshold1
        if threshold2 is not None:
            self.canny_params['threshold2'] = threshold2
        logger.debug(f"Updated Canny parameters: {self.canny_params}")

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
