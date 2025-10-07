"""
Visual Testing Configuration and Fixtures
=========================================

Playwright configuration and visual testing fixtures.
"""

import os
from pathlib import Path

import pytest

# Conditional import for playwright - skip visual tests if not available
try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

    # Create mock fixtures to prevent test collection errors
    @pytest.fixture(scope="session")
    def browser_context_args():
        pytest.skip("Playwright not available")

    @pytest.fixture(scope="session")
    def browser_type_launch_args():
        pytest.skip("Playwright not available")

    @pytest.fixture(scope="function")
    def visual_test_page():
        pytest.skip("Playwright not available")

    @pytest.fixture(scope="function")
    def screenshot_helper():
        pytest.skip("Playwright not available")


# Only define fixtures if playwright is available
if PLAYWRIGHT_AVAILABLE:

    @pytest.fixture(scope="session")
    def browser_context_args():
        """Configure browser context for visual testing."""
        return {
            "viewport": {"width": 1280, "height": 720},
            "ignore_https_errors": True,
            "user_agent": "MVidarr-Visual-Tester/1.0",
        }

    @pytest.fixture(scope="session")
    def browser_type_launch_args():
        """Configure browser launch arguments."""
        return {
            "headless": True,
            "slow_mo": 100,  # Slow down for better screenshots
        }

    @pytest.fixture(scope="function")
    def visual_test_page(page):
        """Configure page for visual testing."""
        # Set longer timeouts for visual tests
        page.set_default_timeout(10000)
        page.set_default_navigation_timeout(30000)

        # Block external resources to speed up tests
        page.route(
            "**/*.{png,jpg,jpeg,gif,webp,svg,woff,woff2,ttf,eot}",
            lambda route: route.abort(),
        )

        return page

    @pytest.fixture(scope="session")
    def screenshots_dir():
        """Get screenshots directory."""
        screenshots_path = Path(__file__).parent / "screenshots"
        screenshots_path.mkdir(exist_ok=True)
        return screenshots_path

    @pytest.fixture(scope="session")
    def baselines_dir():
        """Get baseline images directory."""
        baselines_path = Path(__file__).parent / "baselines"
        baselines_path.mkdir(exist_ok=True)
        return baselines_path

    @pytest.fixture(scope="function")
    def screenshot_helper(visual_test_page, screenshots_dir):
        """Helper for taking and managing screenshots."""

        class ScreenshotHelper:
            def __init__(self, page, screenshots_dir):
                self.page = page
                self.screenshots_dir = screenshots_dir
                self.test_name = None

            def set_test_name(self, name):
                """Set current test name for screenshot naming."""
                self.test_name = name

            def capture_page(self, name=None, full_page=True):
                """Capture full page screenshot."""
                filename = (
                    name or f"{self.test_name}_page.png"
                    if self.test_name
                    else "page.png"
                )
                filepath = self.screenshots_dir / filename

                self.page.screenshot(path=str(filepath), full_page=full_page)
                return filepath

            def capture_element(self, selector, name=None):
                """Capture element screenshot."""
                filename = (
                    name or f"{self.test_name}_element.png"
                    if self.test_name
                    else "element.png"
                )
                filepath = self.screenshots_dir / filename

                element = self.page.locator(selector)
                if element.count() > 0:
                    element.screenshot(path=str(filepath))
                    return filepath
                return None

            def capture_viewport(self, name=None):
                """Capture viewport screenshot."""
                filename = (
                    name or f"{self.test_name}_viewport.png"
                    if self.test_name
                    else "viewport.png"
                )
                filepath = self.screenshots_dir / filename

                self.page.screenshot(path=str(filepath), full_page=False)
                return filepath

            def capture_responsive(self, name_prefix=None):
                """Capture screenshots at different viewport sizes."""
                prefix = name_prefix or self.test_name or "responsive"
                screenshots = {}

                viewports = [
                    ("desktop", 1280, 720),
                    ("tablet", 768, 1024),
                    ("mobile", 375, 667),
                ]

                for device, width, height in viewports:
                    self.page.set_viewport_size({"width": width, "height": height})
                    self.page.wait_for_timeout(500)  # Let layout settle

                    filename = f"{prefix}_{device}.png"
                    filepath = self.screenshots_dir / filename
                    self.page.screenshot(path=str(filepath))
                    screenshots[device] = filepath

                # Reset to default viewport
                self.page.set_viewport_size({"width": 1280, "height": 720})
                return screenshots

        return ScreenshotHelper(visual_test_page, screenshots_dir)


class VisualTestConfig:
    """Visual testing configuration."""

    # Application URL for testing
    BASE_URL = "http://localhost:5000"

    # Screenshot comparison thresholds
    PIXEL_THRESHOLD = 0.2  # 20% pixel difference threshold
    GLOBAL_THRESHOLD = 0.1  # 10% global difference threshold

    # Responsive breakpoints
    BREAKPOINTS = {
        "mobile": {"width": 375, "height": 667},
        "tablet": {"width": 768, "height": 1024},
        "desktop": {"width": 1280, "height": 720},
        "wide": {"width": 1920, "height": 1080},
    }

    # Common UI selectors
    SELECTORS = {
        "navigation": "nav, .navbar, .nav",
        "header": "header, .header",
        "main_content": "main, .main-content, .content",
        "sidebar": ".sidebar, .side-nav, aside",
        "footer": "footer, .footer",
        "modal": ".modal, .dialog, .popup",
        "form": "form, .form",
        "table": "table, .table",
        "video_player": ".video-player, video",
        "settings_panel": ".settings, .config",
    }


@pytest.fixture(scope="session")
def visual_config():
    """Get visual testing configuration."""
    return VisualTestConfig
