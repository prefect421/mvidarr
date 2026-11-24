"""#631: Celery beat used a hard-coded schedule and ignored the Settings page.
Beat now ticks every few minutes and each job decides, from the *saved* settings,
whether it is due. These cover the pure decision logic (all times are UTC)."""

from datetime import datetime, timedelta

import pytest

from src.services.schedule_gate import is_due, parse_schedule


def dt(day, hh, mm=0, month=11, year=2026):
    return datetime(year, month, day, hh, mm)


def due(freq, time_str, last, now):
    return is_due(parse_schedule(freq, time_str), last, now)


class TestIntervals:
    def test_hourly(self):
        now = dt(23, 12, 0)
        assert due("hourly", "02:00", now - timedelta(minutes=59), now) is False
        assert due("hourly", "02:00", now - timedelta(minutes=61), now) is True

    def test_every_n_hours(self):
        now = dt(23, 12, 0)
        assert (
            due("every_3_hours", "00:00", now - timedelta(hours=2, minutes=59), now)
            is False
        )
        assert due("every_3_hours", "00:00", now - timedelta(hours=3), now) is True

    def test_minutes_form_used_by_playlist_sync(self):
        rule = parse_schedule("every_90_minutes", "00:00")
        assert is_due(rule, dt(23, 10, 0), dt(23, 11, 29)) is False
        assert is_due(rule, dt(23, 10, 0), dt(23, 11, 30)) is True


class TestDailyAtATime:
    def test_not_due_before_todays_slot(self):
        assert due("daily", "06:00", dt(22, 6, 1), dt(23, 5, 59)) is False

    def test_due_after_todays_slot(self):
        assert due("daily", "06:00", dt(22, 6, 1), dt(23, 6, 1)) is True

    def test_not_due_again_after_it_already_ran_in_this_slot(self):
        assert due("daily", "06:00", dt(23, 6, 0), dt(23, 6, 5)) is False
        assert due("daily", "06:00", dt(23, 6, 0), dt(23, 20, 0)) is False

    def test_missed_slot_is_caught_up_at_the_next_tick(self):
        # container was down at 06:00; first tick at 14:00 still runs it once
        assert due("daily", "06:00", dt(22, 6, 0), dt(23, 14, 0)) is True


class TestOtherFrequencies:
    def test_twice_daily_slots_12h_apart(self):
        assert due("twice_daily", "06:00", dt(23, 6, 0), dt(23, 17, 59)) is False
        assert due("twice_daily", "06:00", dt(23, 6, 0), dt(23, 18, 1)) is True

    def test_weekly_runs_mondays(self):
        monday, tuesday = dt(23, 7, 0), dt(24, 7, 0)  # 2026-11-23 is a Monday
        assert monday.weekday() == 0
        assert due("weekly", "06:00", dt(16, 6, 0), monday) is True
        assert due("weekly", "06:00", monday.replace(hour=6), tuesday) is False

    def test_named_days(self):
        # Mon 2026-11-23 .. Wed 2026-11-25
        assert (
            due("monday,wednesday", "06:00", dt(23, 6, 0), dt(24, 12, 0)) is False
        )  # Tue
        assert (
            due("monday,wednesday", "06:00", dt(23, 6, 0), dt(25, 6, 30)) is True
        )  # Wed

    def test_single_day_name(self):
        assert due("friday", "06:00", dt(20, 6, 0), dt(27, 6, 1)) is True


class TestBadInput:
    @pytest.mark.parametrize(
        "freq,t",
        [
            ("whenever", "06:00"),
            ("daily", "25:99"),
            ("daily", "oops"),
            ("every_x_hours", "00:00"),
        ],
    )
    def test_unparseable_schedule_is_never_due(self, freq, t):
        assert parse_schedule(freq, t) is None
        assert is_due(None, dt(22, 6, 0), dt(23, 12, 0)) is False
