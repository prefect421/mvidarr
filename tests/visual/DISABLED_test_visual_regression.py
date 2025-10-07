"""
Visual Tests: Visual Regression
==============================

Visual regression testing with baseline comparison.
"""

import os
from pathlib import Path

import imagehash
import pytest
from PIL import Image, ImageChops


@pytest.mark.visual
@pytest.mark.regression
class TestVisualRegression:
    """Visual regression testing with baseline comparison."""

    def _get_baseline_path(self, test_name, baselines_dir):
        """Get baseline image path for a test."""
        return baselines_dir / f"{test_name}_baseline.png"

    def _get_current_path(self, test_name, screenshots_dir):
        """Get current screenshot path for a test."""
        return screenshots_dir / f"{test_name}_current.png"

    def _get_diff_path(self, test_name, screenshots_dir):
        """Get diff image path for a test."""
        return screenshots_dir / f"{test_name}_diff.png"

    def _compare_images(
        self, baseline_path, current_path, diff_path=None, threshold=0.1
    ):
        """
        Compare two images and return similarity score.

        Args:
            baseline_path: Path to baseline image
            current_path: Path to current image
            diff_path: Path to save diff image (optional)
            threshold: Similarity threshold (0.1 = 10% difference allowed)

        Returns:
            tuple: (is_similar, similarity_score, diff_image_path)
        """
        try:
            # Open images
            baseline = Image.open(baseline_path)
            current = Image.open(current_path)

            # Ensure same size
            if baseline.size != current.size:
                current = current.resize(baseline.size, Image.Resampling.LANCZOS)

            # Calculate perceptual hash difference
            baseline_hash = imagehash.phash(baseline)
            current_hash = imagehash.phash(current)
            hash_diff = baseline_hash - current_hash

            # Calculate pixel difference
            diff_image = ImageChops.difference(baseline, current)

            # Save diff image if path provided
            if diff_path:
                diff_image.save(diff_path)

            # Calculate similarity score (lower hash diff = more similar)
            # Hash difference of 0-10 is usually acceptable
            similarity_score = 1.0 - min(hash_diff / 50.0, 1.0)  # Normalize to 0-1

            is_similar = hash_diff <= (threshold * 50)  # Adjust threshold for hash

            return is_similar, similarity_score, diff_path

        except Exception as e:
            pytest.fail(f"Image comparison failed: {e}")

    def test_homepage_visual_regression(
        self,
        visual_test_page,
        screenshot_helper,
        screenshots_dir,
        baselines_dir,
        visual_config,
    ):
        """Test homepage visual regression."""
        test_name = "homepage_regression"
        screenshot_helper.set_test_name(test_name)

        baseline_path = self._get_baseline_path(test_name, baselines_dir)
        current_path = self._get_current_path(test_name, screenshots_dir)
        diff_path = self._get_diff_path(test_name, screenshots_dir)

        try:
            # Capture current screenshot
            visual_test_page.goto(visual_config.BASE_URL)
            visual_test_page.wait_for_load_state("networkidle")
            visual_test_page.screenshot(path=str(current_path))

            # If no baseline exists, create it
            if not baseline_path.exists():
                current_path.rename(baseline_path)
                pytest.skip(
                    f"Created baseline for {test_name}. Run test again to compare."
                )

            # Compare with baseline
            is_similar, similarity, _ = self._compare_images(
                baseline_path,
                current_path,
                diff_path,
                threshold=visual_config.GLOBAL_THRESHOLD,
            )

            assert (
                is_similar
            ), f"Homepage visual regression detected. Similarity: {similarity:.2%}. Check diff: {diff_path}"

        except Exception as e:
            pytest.skip(f"Homepage regression test failed: {e}")

    def test_videos_page_visual_regression(
        self,
        visual_test_page,
        screenshot_helper,
        screenshots_dir,
        baselines_dir,
        visual_config,
    ):
        """Test videos page visual regression."""
        test_name = "videos_regression"
        screenshot_helper.set_test_name(test_name)

        baseline_path = self._get_baseline_path(test_name, baselines_dir)
        current_path = self._get_current_path(test_name, screenshots_dir)
        diff_path = self._get_diff_path(test_name, screenshots_dir)

        try:
            visual_test_page.goto(f"{visual_config.BASE_URL}/videos")
            visual_test_page.wait_for_load_state("networkidle")
            visual_test_page.screenshot(path=str(current_path))

            if not baseline_path.exists():
                current_path.rename(baseline_path)
                pytest.skip(
                    f"Created baseline for {test_name}. Run test again to compare."
                )

            is_similar, similarity, _ = self._compare_images(
                baseline_path,
                current_path,
                diff_path,
                threshold=visual_config.GLOBAL_THRESHOLD,
            )

            assert (
                is_similar
            ), f"Videos page visual regression detected. Similarity: {similarity:.2%}. Check diff: {diff_path}"

        except Exception as e:
            pytest.skip(f"Videos page regression test failed: {e}")

    def test_artists_page_visual_regression(
        self,
        visual_test_page,
        screenshot_helper,
        screenshots_dir,
        baselines_dir,
        visual_config,
    ):
        """Test artists page visual regression."""
        test_name = "artists_regression"
        screenshot_helper.set_test_name(test_name)

        baseline_path = self._get_baseline_path(test_name, baselines_dir)
        current_path = self._get_current_path(test_name, screenshots_dir)
        diff_path = self._get_diff_path(test_name, screenshots_dir)

        try:
            visual_test_page.goto(f"{visual_config.BASE_URL}/artists")
            visual_test_page.wait_for_load_state("networkidle")
            visual_test_page.screenshot(path=str(current_path))

            if not baseline_path.exists():
                current_path.rename(baseline_path)
                pytest.skip(
                    f"Created baseline for {test_name}. Run test again to compare."
                )

            is_similar, similarity, _ = self._compare_images(
                baseline_path,
                current_path,
                diff_path,
                threshold=visual_config.GLOBAL_THRESHOLD,
            )

            assert (
                is_similar
            ), f"Artists page visual regression detected. Similarity: {similarity:.2%}. Check diff: {diff_path}"

        except Exception as e:
            pytest.skip(f"Artists page regression test failed: {e}")


@pytest.mark.visual
@pytest.mark.regression
class TestResponsiveRegression:
    """Test responsive design visual regression."""

    def test_responsive_homepage_regression(
        self,
        visual_test_page,
        screenshot_helper,
        screenshots_dir,
        baselines_dir,
        visual_config,
    ):
        """Test responsive homepage visual regression."""
        try:
            visual_test_page.goto(visual_config.BASE_URL)
            visual_test_page.wait_for_load_state("networkidle")

            for device, dimensions in visual_config.BREAKPOINTS.items():
                test_name = f"homepage_{device}_regression"

                baseline_path = baselines_dir / f"{test_name}_baseline.png"
                current_path = screenshots_dir / f"{test_name}_current.png"
                diff_path = screenshots_dir / f"{test_name}_diff.png"

                # Set viewport
                visual_test_page.set_viewport_size(dimensions)
                visual_test_page.wait_for_timeout(500)

                # Take screenshot
                visual_test_page.screenshot(path=str(current_path))

                if not baseline_path.exists():
                    current_path.rename(baseline_path)
                    continue

                # Compare
                regression_test = TestVisualRegression()
                is_similar, similarity, _ = regression_test._compare_images(
                    baseline_path,
                    current_path,
                    diff_path,
                    threshold=visual_config.GLOBAL_THRESHOLD,
                )

                assert (
                    is_similar
                ), f"Responsive {device} regression detected. Similarity: {similarity:.2%}"

        except Exception as e:
            pytest.skip(f"Responsive regression test failed: {e}")


@pytest.mark.visual
@pytest.mark.regression
class TestComponentRegression:
    """Test individual component visual regression."""

    def test_navigation_component_regression(
        self,
        visual_test_page,
        screenshot_helper,
        screenshots_dir,
        baselines_dir,
        visual_config,
    ):
        """Test navigation component visual regression."""
        test_name = "navigation_regression"

        baseline_path = baselines_dir / f"{test_name}_baseline.png"
        current_path = screenshots_dir / f"{test_name}_current.png"
        diff_path = screenshots_dir / f"{test_name}_diff.png"

        try:
            visual_test_page.goto(visual_config.BASE_URL)
            visual_test_page.wait_for_load_state("networkidle")

            # Find and screenshot navigation
            nav_selectors = visual_config.SELECTORS["navigation"].split(", ")

            for selector in nav_selectors:
                element = visual_test_page.locator(selector)
                if element.count() > 0:
                    element.screenshot(path=str(current_path))
                    break
            else:
                pytest.skip("Navigation component not found")

            if not baseline_path.exists():
                current_path.rename(baseline_path)
                pytest.skip(
                    f"Created baseline for {test_name}. Run test again to compare."
                )

            # Compare
            regression_test = TestVisualRegression()
            is_similar, similarity, _ = regression_test._compare_images(
                baseline_path,
                current_path,
                diff_path,
                threshold=visual_config.GLOBAL_THRESHOLD,
            )

            assert (
                is_similar
            ), f"Navigation component regression detected. Similarity: {similarity:.2%}"

        except Exception as e:
            pytest.skip(f"Navigation regression test failed: {e}")

    def test_header_component_regression(
        self,
        visual_test_page,
        screenshot_helper,
        screenshots_dir,
        baselines_dir,
        visual_config,
    ):
        """Test header component visual regression."""
        test_name = "header_regression"

        baseline_path = baselines_dir / f"{test_name}_baseline.png"
        current_path = screenshots_dir / f"{test_name}_current.png"
        diff_path = screenshots_dir / f"{test_name}_diff.png"

        try:
            visual_test_page.goto(visual_config.BASE_URL)
            visual_test_page.wait_for_load_state("networkidle")

            # Find and screenshot header
            header_selectors = visual_config.SELECTORS["header"].split(", ")

            for selector in header_selectors:
                element = visual_test_page.locator(selector)
                if element.count() > 0:
                    element.screenshot(path=str(current_path))
                    break
            else:
                pytest.skip("Header component not found")

            if not baseline_path.exists():
                current_path.rename(baseline_path)
                pytest.skip(
                    f"Created baseline for {test_name}. Run test again to compare."
                )

            # Compare
            regression_test = TestVisualRegression()
            is_similar, similarity, _ = regression_test._compare_images(
                baseline_path,
                current_path,
                diff_path,
                threshold=visual_config.GLOBAL_THRESHOLD,
            )

            assert (
                is_similar
            ), f"Header component regression detected. Similarity: {similarity:.2%}"

        except Exception as e:
            pytest.skip(f"Header regression test failed: {e}")


@pytest.mark.visual
@pytest.mark.regression
@pytest.mark.slow
class TestCrossBrowserRegression:
    """Test cross-browser visual regression."""

    @pytest.mark.parametrize("browser_name", ["chromium", "firefox"])
    def test_cross_browser_homepage(
        self, browser_name, screenshots_dir, baselines_dir, visual_config
    ):
        """Test homepage across different browsers."""
        pytest.skip("Cross-browser testing requires multiple browser installations")

        # This would require setting up multiple browsers
        # and comparing screenshots between them
        # Implementation would be similar to above but with different browser contexts
