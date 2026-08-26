"""Regression test for a live privilege-escalation incident (2026-08-12):
AuthentikProvider.map_groups_to_role used substring matching
(`admin_group in membership_lower`) instead of exact matching, so any
Authentik group whose name merely CONTAINS "admin"/"manager"/"user" as a
substring granted that MVidarr role — completely disconnected from
whether the group was ever intended to control MVidarr access.

Confirmed live: a user in Authentik's own built-in "authentik Admins"
group (the group for administering Authentik itself, unrelated to
MVidarr) logged into MVidarr via Authentik OAuth and was silently
promoted from USER to ADMIN, because "admins" in "authentik admins" is
True. For any Authentik instance shared across multiple apps, this is a
real privilege-escalation path: any generically-named group containing
these substrings ("IT Admins", "Site Administrators", "Team Managers",
"Existing Users", etc.) grants that role to everyone in it.
"""

from src.database.models import UserRole
from src.services.oauth_service import AuthentikProvider

_PROVIDER_CONFIG = {
    "client_id": "id",
    "client_secret": "secret",
    "redirect_uri": "https://example.test/callback",
    "base_url": "https://auth.example.test",
}


class TestAuthentikRoleMappingUsesExactMatch:
    def setup_method(self):
        self.provider = AuthentikProvider(_PROVIDER_CONFIG)

    def test_unrelated_group_containing_admin_substring_does_not_grant_admin(self):
        """The exact real-world case: Authentik's own built-in
        administrative group, unrelated to MVidarr."""
        role = self.provider.map_groups_to_role(["authentik Admins"], [])
        assert role != UserRole.ADMIN

    def test_unrelated_group_containing_manager_substring_does_not_grant_manager(self):
        role = self.provider.map_groups_to_role(["Team Managers"], [])
        assert role != UserRole.MANAGER

    def test_unrelated_group_containing_user_substring_does_not_grant_user(self):
        role = self.provider.map_groups_to_role(["Existing Users Legacy"], [])
        assert role != UserRole.USER

    def test_exact_admin_group_name_still_grants_admin(self):
        role = self.provider.map_groups_to_role(["admins"], [])
        assert role == UserRole.ADMIN

    def test_exact_mvidarr_admin_group_name_still_grants_admin(self):
        role = self.provider.map_groups_to_role(["mvidarr_admin"], [])
        assert role == UserRole.ADMIN

    def test_exact_match_is_case_insensitive(self):
        role = self.provider.map_groups_to_role(["Administrators"], [])
        assert role == UserRole.ADMIN

    def test_no_matching_group_falls_back_to_readonly(self):
        role = self.provider.map_groups_to_role(["marketing-team"], [])
        assert role == UserRole.READONLY
