"""Static-content regression/feature tests for the #351 login page
redesign: paired background/logo rotation (bg_index, wired in a prior
commit), real OAuth buttons (icon + correct display name instead of the
raw lowercase provider key), and a card that scrolls instead of clipping
when its content overflows.

Matches the static-content-assertion approach already established this
session for template changes (e.g. test_oauth_settings_ui.py,
test_recently_found_videos_ui.py): reads the raw template source, no
browser/render step.
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"
STATIC_DIR = Path(__file__).resolve().parents[2] / "frontend" / "static"


class TestLoginPageRedesign:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "auth" / "login.html").read_text()

    # --- bg_index / paired image rotation ---

    def test_background_image_uses_bg_index(self):
        assert "music/BG/bg' ~ bg_index ~ '.jpg" in self.html.replace('"', "'")

    def test_logo_image_uses_the_same_bg_index(self):
        assert "music/Logo/' ~ bg_index ~ '.png" in self.html.replace('"', "'")

    # --- OAuth buttons: icon + correct display name ---

    def test_oauth_button_shows_an_icon_from_the_provider_keyed_asset(self):
        assert "icons/oauth/' ~ provider ~ '.svg" in self.html.replace('"', "'")

    def test_oauth_button_maps_known_provider_keys_to_display_names(self):
        # Not the raw dict value -- the current template's bug prints
        # oauth_providers.items()'s raw value verbatim, which in
        # production is the lowercase provider id (e.g. "authentik"),
        # not a proper display name.
        assert "'Authentik'" in self.html or '"Authentik"' in self.html
        assert "'Google'" in self.html or '"Google"' in self.html
        assert "'GitHub'" in self.html or '"GitHub"' in self.html

    # --- scrollable card ---

    def test_card_has_a_max_height_and_scrolls(self):
        start = self.html.index(".login-card {")
        end = self.html.index("}", start)
        rule = self.html[start:end]
        assert "max-height" in rule
        assert "overflow-y: auto" in rule

    # --- existing behavior must survive the redesign untouched ---

    def test_existing_element_ids_are_all_still_present(self):
        for element_id in [
            "errorMessage",
            "loginForm",
            "twoFactorForm",
            "twoFactorSection",
            "username",
            "password",
            "loginButton",
            "twoFactorToken",
            "twoFactorButton",
        ]:
            assert f'id="{element_id}"' in self.html, (
                f"#{element_id} is missing -- existing JS binds to this "
                "ID and would silently stop working"
            )

    def test_existing_js_functions_are_still_present(self):
        for marker in [
            "loginForm.addEventListener('submit'",
            "twoFactorForm.addEventListener('submit'",
            "function showError(",
            "function hideError(",
            "oauth_error",
        ]:
            assert marker in self.html


class TestOAuthIconAssetsExist:
    def test_each_provider_icon_file_exists_and_is_an_svg(self):
        for provider in ["authentik", "google", "github"]:
            icon_path = STATIC_DIR / "icons" / "oauth" / f"{provider}.svg"
            assert icon_path.is_file(), f"missing {icon_path}"
            content = icon_path.read_text()
            assert content.strip().startswith("<svg")


class TestBackgroundAndLogoAssetsExist:
    def test_each_paired_bg_and_logo_image_exists(self):
        for n in range(1, 9):
            bg_path = STATIC_DIR / "music" / "BG" / f"bg{n}.jpg"
            logo_path = STATIC_DIR / "music" / "Logo" / f"{n}.png"
            assert bg_path.is_file(), f"missing {bg_path}"
            assert logo_path.is_file(), f"missing {logo_path}"
