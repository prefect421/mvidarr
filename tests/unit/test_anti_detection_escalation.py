"""Tests for AntiDetectionManager.handle_detection_error()'s escalation
logic. Live-reported bug: videos got "All 3 download attempts failed:
unable to download video data: HTTP Error 403: Forbidden" -- tracing
the logs showed all 3 attempts stayed at AntiDetectionLevel.MODERATE.
handle_detection_error() only recognized "Signature extraction failed",
"bot", and "429"/"rate" as escalation triggers; a 403 matched none of
them and fell through to an `else` that unconditionally returned
MODERATE regardless of the current level -- so three "escalating"
retries were functionally identical attempts against the same block.
"""

from unittest.mock import patch

# unified_download_service.py instantiates a module-level singleton
# (UnifiedDownloadService() -> YtDlpManager()) that raises RuntimeError
# if no yt-dlp executable is found on disk -- true in this test venv
# (yt-dlp is only installed inside the mvidarr-dev Docker image, not
# this sandbox). AntiDetectionManager/AntiDetectionLevel themselves
# have no yt-dlp dependency, so patch os.path.exists just long enough
# for the module-level singleton's executable lookup to succeed during
# import, then let it go back to the real implementation for the rest
# of the test run.
with patch("os.path.exists", return_value=True):
    from src.services.unified_download_service import (
        AntiDetectionLevel,
        AntiDetectionManager,
    )


class TestAntiDetectionEscalation:
    def test_403_forbidden_escalates_past_moderate(self):
        manager = AntiDetectionManager()
        result = manager.handle_detection_error(
            "unable to download video data: HTTP Error 403: Forbidden",
            AntiDetectionLevel.MODERATE,
        )
        assert result != AntiDetectionLevel.MODERATE

    def test_403_forbidden_progressively_escalates_on_repeat(self):
        """A second consecutive 403 (now at AGGRESSIVE) must escalate
        further, not return the same level again -- otherwise attempts
        2 and 3 are identical to each other even after the first fix."""
        manager = AntiDetectionManager()
        first = manager.handle_detection_error(
            "unable to download video data: HTTP Error 403: Forbidden",
            AntiDetectionLevel.MODERATE,
        )
        second = manager.handle_detection_error(
            "unable to download video data: HTTP Error 403: Forbidden",
            first,
        )
        assert second != first

    def test_escalation_caps_at_stealth(self):
        manager = AntiDetectionManager()
        result = manager.handle_detection_error(
            "unable to download video data: HTTP Error 403: Forbidden",
            AntiDetectionLevel.STEALTH,
        )
        assert result == AntiDetectionLevel.STEALTH

    def test_signature_extraction_failure_still_jumps_to_aggressive(self):
        """Pre-existing, specifically-diagnosed error signatures keep
        their targeted response -- not swept into the generic
        progressive-escalation path."""
        manager = AntiDetectionManager()
        result = manager.handle_detection_error(
            "Signature extraction failed", AntiDetectionLevel.MODERATE
        )
        assert result == AntiDetectionLevel.AGGRESSIVE

    def test_bot_detection_still_jumps_to_stealth(self):
        manager = AntiDetectionManager()
        result = manager.handle_detection_error(
            "Confirm you're not a bot", AntiDetectionLevel.MODERATE
        )
        assert result == AntiDetectionLevel.STEALTH

    def test_rate_limit_still_jumps_to_aggressive(self):
        manager = AntiDetectionManager()
        result = manager.handle_detection_error(
            "HTTP Error 429: Too Many Requests", AntiDetectionLevel.MODERATE
        )
        assert result == AntiDetectionLevel.AGGRESSIVE
