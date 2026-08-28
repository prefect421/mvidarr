"""Regression test for issue #485: the MKV transcoding notice on the video
detail page had no way to dismiss it, and stayed on-screen for every video
even after a viewer had already seen it.

Fix: the notice now renders a close button that hides it for the current
view, plus a "Don't show this again" link that persists the dismissal in
localStorage (key `mvidarr_hide_mkv_warning`) so the notice stops rendering
on future page loads.

Code review on the first version of this fix caught a real bug: the close
button's dismissal only did `notice.style.display = 'none'` on the live DOM
node, with nothing recorded outside it. `renderVideoDetails()` re-runs on
every `loadVideoDetails()` refresh -- which several routine same-page
actions trigger (starting a download, enhancing metadata, saving an edit,
a quality upgrade) -- so the notice silently reappeared on the very next
refresh, undoing the dismissal. The fix adds a page-scoped
`mkvNoticeTemporarilyDismissed` flag, declared outside `renderVideoDetails`
so it survives across repeated calls within the same page view, and set
unconditionally in `dismissMkvWarning()` regardless of the `permanent` arg.
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

    def test_render_gate_also_checks_the_same_view_dismissal_flag(self):
        # Regression: without this, a "x" dismissal was silently undone by
        # any same-page action that refreshes video details (download
        # start, metadata enhancement, edits, quality upgrades all call
        # loadVideoDetails() -> renderVideoDetails() again).
        start = self.html.index("const playerHtml = `")
        end = self.html.index("</video>", start)
        render_block = self.html[start:end]
        assert "!mkvNoticeTemporarilyDismissed" in render_block

    def test_temporary_dismissal_flag_is_scoped_outside_the_render_function(self):
        # The flag must be declared above renderVideoDetails (module/script
        # scope), not re-initialized inside it -- otherwise it would reset
        # to false on every call and never actually persist across
        # same-view re-renders.
        declare_at = self.html.index("let mkvNoticeTemporarilyDismissed = false;")
        render_fn_at = self.html.index("function renderVideoDetails(video) {")
        assert declare_at < render_fn_at

    def test_dismiss_handler_sets_temporary_flag_unconditionally(self):
        # Must be set regardless of `permanent` -- a plain "x" close (not
        # "don't show again") still needs to survive same-view re-renders.
        start = self.html.index("function dismissMkvWarning(")
        end = self.html.index("\n}", start)
        body = self.html[start:end]
        set_flag_at = body.index("mkvNoticeTemporarilyDismissed = true;")
        if_permanent_at = body.index("if (permanent)")
        assert set_flag_at < if_permanent_at

    def test_stored_preference_is_read_defensively(self):
        # localStorage access can throw (private browsing, blocked site
        # data); the read must not be able to break page rendering.
        start = self.html.index("hideMkvWarning = false;")
        end = self.html.index("const playerHtml", start)
        setup_block = self.html[start:end]
        assert "try {" in setup_block
        assert "localStorage.getItem('mvidarr_hide_mkv_warning')" in setup_block
