"""Regression test: the MKV transcoding notice ("MKV file detected --
using real-time transcoding for browser compatibility.") rendered as
white text on its own light-beige (#fff3cd) background, making it
unreadable.

Root cause: .video-transcoding-notice sets color: #856404 on the
container, but its <p> children inherit that color -- and
frontend/CSS/typography.css's global `p, .text-base { color:
var(--text-primary); }` rule directly targets the <p> element itself.
A rule that directly targets an element always wins over a color
merely inherited from an ancestor, regardless of the ancestor rule's
specificity -- var(--text-primary) is white in the default dark theme,
so the notice's <p> text rendered white on its light-yellow/beige
background.

Fix: give `.video-transcoding-notice p` its own explicit color,
matching the container's intended brown, so it's no longer relying on
an inheritance path that a same-page global rule can steal.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestTranscodingNoticeContrast:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "video_detail.html").read_text()

    def _rule_body(self, selector):
        start = self.html.index(selector)
        # The rule's own explanatory comment quotes a snippet containing a
        # literal "}" (typography.css's colliding rule) -- skip past any
        # comment block before looking for the rule's real closing brace.
        comment_end = self.html.find("*/", start)
        search_from = comment_end + 2 if comment_end != -1 else start
        end = self.html.index("}", search_from)
        return self.html[start:end]

    def test_notice_paragraphs_have_an_explicit_color_not_just_inherited(self):
        rule = self._rule_body(".video-transcoding-notice p {")
        assert "color:" in rule

    def test_notice_paragraph_color_matches_the_container_not_white(self):
        rule = self._rule_body(".video-transcoding-notice p {")
        # Only the last "color:" declaration in the rule is the one that
        # actually applies -- the explanatory comment's quoted snippet
        # also contains the substring "color:", so check the real
        # declaration specifically, not just presence anywhere in the
        # slice.
        declarations = [line.strip() for line in rule.splitlines() if "color:" in line]
        real_declaration = next(d for d in declarations if d.startswith("color:"))
        assert "#856404" in real_declaration
        assert "var(--text-primary)" not in real_declaration
