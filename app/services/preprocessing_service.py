"""
Preprocessing service for ML pipelines.

Implements Hampel filtering for price series cleaning.
"""
from typing import List, Tuple, Optional
from statistics import median
import logging

logger = logging.getLogger(__name__)


class PreprocessingService:
    """
    Clean price data for ML using Hampel filter (MAD-based outlier detection).
    
    Hampel filter:
        MAD = median(|x_i - median(x)|)
        Outlier if |x_i - median(x)| > threshold * MAD
    """

    @staticmethod
    def clean_price_series(
        prices: List[float],
        window: int = 20,
        threshold: float = 3.5,
    ) -> Tuple[List[float], List[int]]:
        """
        Apply Hampel filter to remove price outliers.
        
        Args:
            prices: List of price points
            window: Rolling window size for MAD calculation
            threshold: MAD threshold for outlier detection (default 3.5)
            
        Returns:
            (cleaned_prices, outlier_indices)
        """
        if len(prices) < window:
            logger.debug(f"Price series too short ({len(prices)} < {window}); skipping")
            return prices, []

        cleaned = prices.copy()
        outliers = []

        # Rolling Hampel filter
        for i in range(window // 2, len(prices) - window // 2):
            window_start = i - window // 2
            window_end = i + window // 2
            window_prices = prices[window_start:window_end]

            median_val = median(window_prices)
            mad = median([abs(p - median_val) for p in window_prices])

            if mad == 0:
                continue

            # Check if outlier
            if abs(prices[i] - median_val) > threshold * mad:
                outliers.append(i)
                cleaned[i] = median_val
                logger.debug(
                    f"Outlier at {i}: price={prices[i]:.4f}, median={median_val:.4f}"
                )

        logger.info(f"Cleaned {len(prices)} prices: {len(outliers)} outliers removed")
        return cleaned, outliers

    @staticmethod
    def detect_price_gaps(
        prices: List[float],
        gap_threshold_pct: float = 5.0,
    ) -> List[int]:
        """
        Detect significant price gaps (>gap_threshold_pct).
        
        Args:
            prices: List of prices
            gap_threshold_pct: Gap threshold as percentage
            
        Returns:
            List of indices where gaps detected
        """
        if len(prices) < 2:
            return []

        gaps = []
        for i in range(1, len(prices)):
            if prices[i - 1] == 0:
                continue
            pct_change = abs(prices[i] - prices[i - 1]) / prices[i - 1] * 100
            if pct_change > gap_threshold_pct:
                gaps.append(i)

        logger.debug(f"Detected {len(gaps)} price gaps")
        return gaps

    @staticmethod
    def interpolate_missing(
        values: List[Optional[float]],
        method: str = "linear",
    ) -> List[float]:
        """
        Interpolate missing values (None) in series.
        
        Args:
            values: List with potential None values
            method: "linear", "forward_fill", or "mean"
            
        Returns:
            List with missing values interpolated
        """
        if not values:
            return []

        result = values.copy()
        indices = [i for i, v in enumerate(result) if v is not None]

        if len(indices) < 2:
            return [v if v is not None else 0.0 for v in result]

        for i in range(len(result)):
            if result[i] is None:
                if method == "linear":
                    left_idx = max([idx for idx in indices if idx < i], default=0)
                    right_idx = min([idx for idx in indices if idx > i], default=len(result) - 1)
                    if left_idx < i < right_idx:
                        frac = (i - left_idx) / (right_idx - left_idx)
                        result[i] = result[left_idx] + frac * (result[right_idx] - result[left_idx])
                    else:
                        result[i] = result[left_idx] if left_idx < i else result[right_idx]
                elif method == "forward_fill":
                    result[i] = result[i - 1] if i > 0 else 0.0
                elif method == "mean":
                    non_null = [v for v in result if v is not None]
                    result[i] = sum(non_null) / len(non_null) if non_null else 0.0

        return result

    @staticmethod
    def normalize_features(
        features: List[List[float]],
    ) -> Tuple[List[List[float]], dict]:
        """
        Normalize features to mean=0, std=1.
        
        Args:
            features: List of feature vectors
            
        Returns:
            (normalized_features, normalization_params)
        """
        if not features or not features[0]:
            return features, {}

        n_features = len(features[0])
        means = []
        stds = []

        for feat_idx in range(n_features):
            feat_values = [f[feat_idx] for f in features]
            mean_val = sum(feat_values) / len(feat_values)
            variance = sum((v - mean_val) ** 2 for v in feat_values) / len(feat_values)
            std_val = variance ** 0.5
            means.append(mean_val)
            stds.append(std_val if std_val > 0 else 1.0)

        # Normalize
        normalized = [
            [(f[i] - means[i]) / stds[i] for i in range(n_features)]
            for f in features
        ]

        logger.debug(f"Normalized {len(features)} samples, {n_features} features")
        return normalized, {"means": means, "stds": stds}
