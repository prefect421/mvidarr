"""Tests for TwoFactorService's pending-ticket mechanism, which binds
verify-login to a prior password check (see the 2026-08-10 revision to
Task 9 — the original username-based contract had no such binding,
letting anyone with a guessed/stolen TOTP code log in without a password
at all)."""

from src.services.two_factor_service import TwoFactorService, _pending_2fa_tickets


def setup_function():
    _pending_2fa_tickets.clear()


class TestPendingTicket:
    def test_consume_returns_the_user_id_the_ticket_was_issued_for(self):
        ticket = TwoFactorService.create_pending_ticket(42)
        assert TwoFactorService.consume_pending_ticket(ticket) == 42

    def test_consume_is_single_use(self):
        ticket = TwoFactorService.create_pending_ticket(42)
        TwoFactorService.consume_pending_ticket(ticket)
        assert TwoFactorService.consume_pending_ticket(ticket) is None

    def test_consume_rejects_unknown_ticket(self):
        assert TwoFactorService.consume_pending_ticket("never-issued") is None

    def test_consume_rejects_expired_ticket(self):
        from datetime import datetime, timedelta
        from unittest.mock import patch

        ticket = TwoFactorService.create_pending_ticket(42)
        future = datetime.utcnow() + timedelta(minutes=10)
        with patch("src.services.two_factor_service.datetime") as mock_dt:
            mock_dt.utcnow.return_value = future
            assert TwoFactorService.consume_pending_ticket(ticket) is None
