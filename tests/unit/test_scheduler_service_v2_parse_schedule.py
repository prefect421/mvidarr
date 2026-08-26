"""#317: SchedulerServiceV2 (566 lines) had zero test coverage --
explicitly the issue's own top concern ("changed the most... carries
the most regression risk of any subsystem"). _parse_schedule() is its
richest pure-logic surface: no DB, no Celery connection, no
subprocess -- just frequency-string + time-string parsing into
celery.schedules objects that actually govern when auto-discovery and
auto-download run. A silent bug here doesn't crash anything -- it just
means an artist quietly never gets checked, which is exactly the kind
of regression that goes unnoticed for weeks.

celery.schedules.crontab normalizes hour/minute/day_of_week into sets
(e.g. crontab(hour=14) -> hour == {14}), and defaults any unspecified
field to "every value" (e.g. no day_of_week -> all 7 days) -- assertions
below match against those actual set values, not raw ints.

While writing these, TestParseScheduleCommaSeparatedDays found a real
bug (not a bad test assumption): the day-name branch was gated behind
`if "," in frequency:`, so a single day name with no comma (e.g. just
"monday") never reached day-name parsing at all -- it fell through to
"Unknown schedule frequency" and silently scheduled nothing. A single
selected day is a thoroughly plausible real input (any UI letting a
user pick just one day of the week). Fixed alongside these tests: the
comma check is gone, `frequency.split(",")` already handles a
comma-less single value correctly (returns a 1-element list).
"""

from datetime import timedelta

import pytest
from celery.schedules import crontab
from celery.schedules import schedule as celery_schedule

from src.services.scheduler_service_v2 import SchedulerServiceV2

ALL_DAYS = {0, 1, 2, 3, 4, 5, 6}


def _service():
    # Bypass __init__()'s celery_app/get_db wiring -- _parse_schedule()
    # touches neither.
    return SchedulerServiceV2.__new__(SchedulerServiceV2)


class TestParseScheduleHourly:
    def test_hourly_ignores_the_time_string_and_runs_every_hour(self):
        result = _service()._parse_schedule("hourly", "09:15")
        assert isinstance(result, celery_schedule)
        assert result.run_every == timedelta(hours=1)


class TestParseScheduleDaily:
    def test_daily_runs_at_the_given_hour_and_minute_every_day(self):
        result = _service()._parse_schedule("daily", "14:30")
        assert isinstance(result, crontab)
        assert result.hour == {14}
        assert result.minute == {30}
        assert result.day_of_week == ALL_DAYS

    def test_daily_at_midnight(self):
        result = _service()._parse_schedule("daily", "00:00")
        assert result.hour == {0}
        assert result.minute == {0}


class TestParseScheduleWeekly:
    def test_weekly_runs_on_monday_at_the_given_time(self):
        result = _service()._parse_schedule("weekly", "03:00")
        assert isinstance(result, crontab)
        assert result.hour == {3}
        assert result.minute == {0}
        assert result.day_of_week == {1}  # Monday


class TestParseScheduleTwiceDaily:
    def test_twice_daily_runs_at_the_given_hour_and_12_hours_later(self):
        result = _service()._parse_schedule("twice_daily", "06:00")
        assert isinstance(result, crontab)
        assert result.hour == {6, 18}
        assert result.minute == {0}

    def test_twice_daily_wraps_around_midnight(self):
        # 20:00 + 12h = 32 -> wraps to 8 via % 24
        result = _service()._parse_schedule("twice_daily", "20:00")
        assert result.hour == {20, 8}


class TestParseScheduleEveryNHours:
    def test_every_n_hours_parses_the_interval(self):
        result = _service()._parse_schedule("every_6_hours", "00:00")
        assert isinstance(result, celery_schedule)
        assert result.run_every == timedelta(hours=6)

    def test_every_n_hours_with_a_single_digit(self):
        result = _service()._parse_schedule("every_2_hours", "00:00")
        assert result.run_every == timedelta(hours=2)

    def test_every_n_hours_with_a_non_numeric_n_returns_none(self):
        result = _service()._parse_schedule("every_soon_hours", "00:00")
        assert result is None

    def test_bare_every_with_no_number_returns_none(self):
        result = _service()._parse_schedule("every_", "00:00")
        assert result is None


class TestParseScheduleCommaSeparatedDays:
    def test_single_named_day(self):
        result = _service()._parse_schedule("monday", "10:00")
        assert isinstance(result, crontab)
        assert result.day_of_week == {1}
        assert result.hour == {10}

    def test_multiple_named_days_are_comma_separated(self):
        result = _service()._parse_schedule("monday,wednesday,friday", "10:00")
        assert isinstance(result, crontab)
        assert result.day_of_week == {1, 3, 5}

    def test_sunday_maps_to_zero_not_seven(self):
        result = _service()._parse_schedule("sunday", "10:00")
        assert result.day_of_week == {0}

    def test_day_names_are_case_and_whitespace_insensitive(self):
        result = _service()._parse_schedule(" Monday , TUESDAY ", "10:00")
        assert result.day_of_week == {1, 2}

    def test_a_mix_of_valid_and_invalid_day_names_keeps_only_the_valid_ones(self):
        result = _service()._parse_schedule("monday,notaday,friday", "10:00")
        assert result.day_of_week == {1, 5}

    def test_all_invalid_day_names_returns_none(self):
        result = _service()._parse_schedule("notaday,alsoNotADay", "10:00")
        assert result is None


class TestParseScheduleUnknownOrMalformed:
    def test_a_single_unrecognized_word_with_no_comma_returns_none(self):
        # No comma -> never reaches the day-name parsing branch at all.
        result = _service()._parse_schedule("fortnightly", "10:00")
        assert result is None

    def test_malformed_time_string_is_caught_and_returns_none(self):
        result = _service()._parse_schedule("daily", "not-a-time")
        assert result is None

    def test_empty_frequency_returns_none(self):
        result = _service()._parse_schedule("", "10:00")
        assert result is None
