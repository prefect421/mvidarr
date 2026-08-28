"""Regression test for issue #485: the MKV transcoding notice on the video
detail page had no way to dismiss it, and stayed on-screen for every video
even after a viewer had already seen it.

Fix: the notice now renders a close button that hides it for the current
view, plus a "Don't show this again" link that persists the dismissal in
localStorage (key `mvidarr_hide_mkv_warning`) so the notice stops rendering
on future page loads.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestMkvWarningDismissible:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "video_detail.html").read_text()

    def test_notice_has_a_close_button(self):
        assert 'id="mkvTranscodingNotice"' in self.html
        assert 'onclick="dismissMkvWarning(false)"' in self.html

    def test_notice_has_a_dont_show_again_option(self):
        assert 'onclick="dismissMkvWarning(true); return false;"' in self.html

    def test_dismiss_handler_persists_permanent_choice_in_localstorage(self):
        start = self.html.index("function dismissMkvWarning(")
        end = self.html.index("\n}", start)
        body = self.html[start:end]
        assert "localStorage.setItem('mvidarr_hide_mkv_warning', 'true')" in body

    def test_render_checks_stored_preference_before_showing_notice(self):
        # The notice's render condition must consult the stored flag, not
        # just `needsTranscoding` alone, or a permanent dismissal would be
        # ignored on the next page load.
        start = self.html.index("const playerHtml = `")
        end = self.html.index("</video>", start)
        render_block = self.html[start:end]
        assert "needsTranscoding && !hideMkvWarning" in render_block

    def test_stored_preference_is_read_defensively(self):
        # localStorage access can throw (private browsing, blocked site
        # data); the read must not be able to break page rendering.
        start = self.html.index("hideMkvWarning = false;")
        end = self.html.index("const playerHtml", start)
        setup_block = self.html[start:end]
        assert "try {" in setup_block
        assert "localStorage.getItem('mvidarr_hide_mkv_warning')" in setup_block
