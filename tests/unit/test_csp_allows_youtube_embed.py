"""Live-reported: playing a video with no local file falls back to a
YouTube <iframe> embed (videos.html's playVideo()), a legitimate,
intentional preview feature for MONITORED/not-yet-downloaded videos.
The Content-Security-Policy header had no frame-src directive, so it
fell back to default-src 'self' -- which browsers correctly enforce
by blocking ANY iframe embed, including YouTube's, breaking the
feature outright with a CSP violation in the console:

  Content-Security-Policy: The page's settings blocked the loading of
  a resource (frame-src) at https://www.youtube.com/embed/<id> because
  it violates the following directive: "default-src 'self'"

Fix: SecurityValidationMiddleware.SECURITY_HEADERS' CSP now includes
an explicit frame-src allowing only the YouTube embed origins the
feature actually needs -- not a blanket allowance.
"""

from src.middleware.security_validation_middleware import SecurityValidationConfig


class TestContentSecurityPolicyAllowsYoutubeEmbed:
    def test_csp_includes_frame_src_for_youtube(self):
        csp = SecurityValidationConfig.SECURITY_HEADERS["Content-Security-Policy"]
        directives = {
            d.strip().split(" ")[0]: d.strip() for d in csp.split(";") if d.strip()
        }

        assert "frame-src" in directives, (
            "CSP has no frame-src directive -- falls back to default-src "
            "'self', blocking the YouTube embed fallback in playVideo()"
        )
        frame_src = directives["frame-src"]
        assert "https://www.youtube.com" in frame_src
        assert "https://www.youtube-nocookie.com" in frame_src

    def test_csp_still_denies_arbitrary_framing_by_default(self):
        # The fix must be a targeted allowance, not a blanket relaxation --
        # frame-ancestors (whether THIS app can be framed by others) is a
        # separate, unrelated directive and must stay locked down.
        csp = SecurityValidationConfig.SECURITY_HEADERS["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp
