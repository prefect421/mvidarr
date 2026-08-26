"""Fix for #389: non-admin users got no graceful UI degradation on
admin-gated Spotify/Last.fm/system-health buttons. Buttons like "Connect
Spotify," "Disconnect," "Test Connection," and the System Health link were
visible to any authenticated user, but clicking them hit a require_admin
API endpoint and 403'd -- confusingly, since the frontend's global 401
interceptor doesn't handle 403.

Fix (frontend-hiding, per the issue's own recommendation): every control
that maps to a require_admin-gated endpoint gets a shared
admin-only-control class. base.html defines
`body.non-admin-user .admin-only-control { display: none !important; }`
and checkUserAuthentication() toggles the non-admin-user body class from
data.user.can_admin (role_permissions()'s pre-computed, deliberately
ADMIN-only flag -- see src/api/fastapi/auth.py -- which already matches
auth_dependencies.require_admin's real backend check exactly, so the
frontend doesn't duplicate that role-comparison logic itself). The
!important body-class rule (rather than setting each element's inline
style once) matters for lastfm.html specifically: its
checkLastFmStatus() independently flips #connectBtn/#disconnectBtn
between display:none and visible based on connection state, and the CSS
rule must win regardless of which runs last.

Static-content-assertion approach, matching the pattern already
established for this app's other template regression tests (e.g.
test_recently_found_videos_ui.py, test_oauth_settings_ui.py).
"""

from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"


class TestBaseHtmlAdminOnlyMechanism:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "base.html").read_text()

    def test_css_rule_hides_admin_only_controls_for_non_admin_body_class(self):
        assert "body.non-admin-user .admin-only-control" in self.html
        start = self.html.index("body.non-admin-user .admin-only-control")
        end = self.html.index("}", start)
        rule = self.html[start:end]
        assert "display: none !important" in rule

    def test_check_user_authentication_toggles_the_body_class_from_can_admin(self):
        start = self.html.index("function checkUserAuthentication()")
        end = self.html.index("\n        }", start)
        body = self.html[start:end]
        assert "data.user.can_admin" in body
        assert "non-admin-user" in body

    def test_fails_closed_when_auth_check_itself_errors(self):
        # A network error or non-2xx response resolving checkUserAuthentication
        # must not leave admin-only controls visible by default.
        start = self.html.index("function checkUserAuthentication()")
        end = self.html.index("\n        }\n        \n", start)
        body = self.html[start:end]
        assert body.count("non-admin-user") >= 3  # success, failure, catch branches


class TestSettingsHtmlAdminOnlyControls:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "settings.html").read_text()

    def test_spotify_test_connection_is_admin_only(self):
        assert (
            'onclick="testSpotifyIntegration()" class="btn btn-info admin-only-control"'
            in self.html
        )

    def test_spotify_authorize_is_admin_only(self):
        assert (
            'onclick="authorizeSpotify()" class="btn btn-success admin-only-control"'
            in self.html
        )

    def test_spotify_import_playlists_is_not_admin_only(self):
        # /api/spotify/import-playlists is require_authentication, not
        # require_admin -- must stay usable by any logged-in user.
        assert (
            'onclick="importSpotifyPlaylists()" class="btn btn-secondary">' in self.html
        )
        assert (
            'onclick="importSpotifyPlaylists()" class="btn btn-secondary admin-only-control"'
            not in self.html
        )

    def test_lastfm_test_connection_is_admin_only(self):
        assert (
            'onclick="testLastfmIntegration()" class="btn btn-info admin-only-control"'
            in self.html
        )

    def test_lastfm_authorize_is_admin_only(self):
        assert (
            'onclick="authorizeLastfm()" class="btn btn-success admin-only-control"'
            in self.html
        )

    def test_lastfm_sync_history_is_not_admin_only(self):
        # /api/lastfm/sync-history is require_authentication, not
        # require_admin -- must stay usable by any logged-in user.
        assert 'onclick="syncLastfmHistory()" class="btn btn-secondary">' in self.html
        assert (
            'onclick="syncLastfmHistory()" class="btn btn-secondary admin-only-control"'
            not in self.html
        )

    def test_system_health_tool_card_is_admin_only(self):
        # /system-health and every one of its backing API routes require
        # require_admin -- the whole card is gated, not just the link.
        start = self.html.index("System Health Tool")
        end = self.html.index("</div>", start)
        card_open_tag = self.html[start:end]
        assert 'class="tool-card admin-only-control"' in card_open_tag


class TestSpotifyHtmlAdminOnlyControls:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "spotify.html").read_text()

    def test_test_connection_is_admin_only(self):
        assert (
            'onclick="testConnection()" class="btn btn-info admin-only-control"'
            in self.html
        )

    def test_authorize_is_admin_only(self):
        assert (
            'onclick="authorize()" class="btn btn-success admin-only-control"'
            in self.html
        )

    def test_disconnect_is_admin_only(self):
        assert (
            'onclick="disconnect()" class="btn btn-danger admin-only-control"'
            in self.html
        )

    def test_load_playlists_is_not_admin_only(self):
        # /api/spotify/playlists is require_authentication, not
        # require_admin.
        assert 'onclick="loadPlaylists()" class="btn btn-primary">' in self.html


class TestLastfmHtmlAdminOnlyControls:
    def setup_method(self):
        self.html = (TEMPLATES_DIR / "lastfm.html").read_text()

    def test_connect_button_is_admin_only(self):
        assert 'id="connectBtn"' in self.html
        start = self.html.index('id="connectBtn"')
        end = self.html.index(">", start)
        tag = self.html[start:end]
        assert "admin-only-control" in tag

    def test_disconnect_button_is_admin_only(self):
        assert 'id="disconnectBtn"' in self.html
        start = self.html.index('id="disconnectBtn"')
        end = self.html.index(">", start)
        tag = self.html[start:end]
        assert "admin-only-control" in tag

    def test_authenticate_button_is_admin_only(self):
        assert (
            'onclick="authenticateWithLastFm()" class="btn btn-primary admin-only-control"'
            in self.html
        )

    def test_refresh_top_artists_is_not_admin_only(self):
        # Refresh/import buttons hit require_authentication endpoints,
        # not require_admin.
        assert (
            'onclick="refreshTopArtists()" class="btn btn-sm btn-secondary">'
            in self.html
        )
