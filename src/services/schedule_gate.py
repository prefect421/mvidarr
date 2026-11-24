"""Decide, from the *saved* settings, which scheduled jobs are due (#631).

Celery beat used a hard-coded schedule (downloads every 2h, discovery and playlist
sync every 6h) and never read the Settings page: the schedule update ran in the
web process and only changed that process's memory, while beat is a separate
program. Rather than add a database-backed beat scheduler, beat now fires one cheap
"tick" every few minutes, and each tick asks :func:`due_jobs` which jobs are due.
Changes saved in Settings therefore apply on the next tick, with no restart.

Schedule vocabulary (the same one the Settings page and ``SchedulerServiceV2``
already use; times are UTC, as beat's crontab always was):
  hourly | every_N_hours | every_N_minutes
  daily | twice_daily | weekly (Mondays) | monday,wednesday,...   (all "at HH:MM")

Slot schedules are catch-up: if the container was down at the slot, the job runs at
the next tick once. The last run is read from, and claimed in, the database (not the
per-process settings cache), with a compare-and-set, so several worker processes or
overlapping ticks can never run the same job twice.
"""

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Dict, FrozenSet, List, Optional, Tuple

from sqlalchemy.exc import IntegrityError

from src.database.connection import get_db
from src.database.models import Setting
from src.services.settings_service import SettingsService
from src.utils.logger import get_logger

logger = get_logger("mvidarr.schedule_gate")

_DAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(frozen=True)
class Rule:
    interval: Optional[timedelta] = None
    weekdays: Optional[FrozenSet[int]] = None  # python weekday(): Monday == 0
    times: Tuple[Tuple[int, int], ...] = ()


def _parse_hhmm(value: str) -> Optional[Tuple[int, int]]:
    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value or "")
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    return (hour, minute) if hour < 24 and minute < 60 else None


def parse_schedule(frequency: str, time_str: str) -> Optional[Rule]:
    """A :class:`Rule` for a saved frequency/time, or None if it is not understood."""
    freq = (frequency or "").strip().lower()

    if freq == "hourly":
        return Rule(interval=timedelta(hours=1))
    m = re.fullmatch(r"every_(\d+)_(hours?|minutes?)", freq)
    if m and int(m.group(1)) > 0:
        n = int(m.group(1))
        unit = "hours" if m.group(2).startswith("hour") else "minutes"
        return Rule(interval=timedelta(**{unit: n}))

    hhmm = _parse_hhmm(time_str)
    if hhmm is None:
        return None
    hour, minute = hhmm
    every_day = frozenset(range(7))
    if freq == "daily":
        return Rule(weekdays=every_day, times=((hour, minute),))
    if freq == "twice_daily":
        return Rule(
            weekdays=every_day, times=((hour, minute), ((hour + 12) % 24, minute))
        )
    if freq == "weekly":
        return Rule(weekdays=frozenset({0}), times=((hour, minute),))
    names = [d.strip() for d in freq.split(",") if d.strip()]
    if names and all(n in _DAYS for n in names):
        return Rule(
            weekdays=frozenset(_DAYS[n] for n in names), times=((hour, minute),)
        )
    return None


def _latest_slot(rule: Rule, now: datetime) -> Optional[datetime]:
    for back in range(8):
        day = (now - timedelta(days=back)).date()
        if day.weekday() not in rule.weekdays:
            continue
        slots = [datetime.combine(day, time(h, m)) for h, m in rule.times]
        past = [s for s in slots if s <= now]
        if past:
            return max(past)
    return None


def is_due(rule: Optional[Rule], last_run: Optional[datetime], now: datetime) -> bool:
    if rule is None:
        return False
    if last_run is None:
        return True
    if rule.interval is not None:
        return now - last_run >= rule.interval
    slot = _latest_slot(rule, now)
    return slot is not None and last_run < slot


# ----------------------------------------------------------------------------
# Jobs and settings
# ----------------------------------------------------------------------------


@dataclass(frozen=True)
class JobSpec:
    key: str
    task: str
    enabled_key: Optional[str] = None
    days_key: Optional[str] = None
    time_key: Optional[str] = None
    default_days: str = "daily"
    default_time: str = "06:00"
    interval_minutes_key: Optional[str] = None
    default_interval_minutes: int = 360


JOBS: Dict[str, JobSpec] = {
    "discovery": JobSpec(
        key="discovery",
        task="src.tasks.scheduled_tasks.scheduled_discovery_task",
        enabled_key="auto_discovery_schedule_enabled",
        days_key="auto_discovery_schedule_days",
        time_key="auto_discovery_schedule_time",
        default_days="daily",
        default_time="06:00",
    ),
    "downloads": JobSpec(
        key="downloads",
        task="src.tasks.scheduled_tasks.scheduled_downloads_task",
        enabled_key="auto_download_schedule_enabled",
        days_key="auto_download_schedule_days",
        time_key="auto_download_schedule_time",
        default_days="hourly",
        default_time="02:00",
    ),
    # the Settings page's "Playlist Sync Interval (minutes)"; previously never read
    "playlist-sync": JobSpec(
        key="playlist-sync",
        task="src.tasks.scheduled_tasks.playlist_sync_task",
        interval_minutes_key="youtube_playlist_sync_interval",
        default_interval_minutes=360,
    ),
}


def rule_for(spec: JobSpec) -> Tuple[bool, Optional[Rule], str]:
    """(enabled, rule, human description) from the currently saved settings."""
    if spec.interval_minutes_key:
        minutes = max(
            5,
            SettingsService.get_int(
                spec.interval_minutes_key, spec.default_interval_minutes
            ),
        )
        return (
            True,
            parse_schedule(f"every_{minutes}_minutes", "00:00"),
            f"every {minutes} minutes",
        )
    enabled = SettingsService.get_bool(spec.enabled_key, True)
    days = SettingsService.get(spec.days_key, spec.default_days) or spec.default_days
    at = SettingsService.get(spec.time_key, spec.default_time) or spec.default_time
    return enabled, parse_schedule(days, at), f"{days} at {at} UTC"


def _last_run_key(spec: JobSpec) -> str:
    return f"scheduler_last_run_{spec.key}"


def _read_last_run(session, spec: JobSpec) -> Tuple[Optional[str], Optional[datetime]]:
    row = session.query(Setting).filter(Setting.key == _last_run_key(spec)).first()
    raw = row.value if row else None
    if not raw:
        return raw, None
    try:
        return raw, datetime.fromisoformat(raw)
    except ValueError:
        return raw, None


def _claim(session, spec: JobSpec, expected_old: Optional[str], now: datetime) -> bool:
    """Record this run unless another process already did (compare-and-set)."""
    stamp = now.isoformat()
    key = _last_run_key(spec)
    try:
        if expected_old is None:
            session.add(
                Setting(
                    key=key,
                    value=stamp,
                    description=f"Last scheduled run of {spec.key} (UTC)",
                )
            )
            session.commit()
            return True
        changed = (
            session.query(Setting)
            .filter(Setting.key == key, Setting.value == expected_old)
            .update({"value": stamp}, synchronize_session=False)
        )
        session.commit()
        return changed == 1
    except IntegrityError:
        session.rollback()
        return False


def due_jobs(now: Optional[datetime] = None) -> List[str]:
    """Task names whose saved schedule says they should run now (claims each run)."""
    now = now or datetime.utcnow()
    run: List[str] = []
    for spec in JOBS.values():
        try:
            enabled, rule, description = rule_for(spec)
            if not enabled:
                continue
            if rule is None:
                logger.warning(
                    f"Scheduler: could not understand the saved schedule for {spec.key}; skipping"
                )
                continue
            with get_db() as session:
                raw, last_run = _read_last_run(session, spec)
                if last_run is None:
                    # First time we see this job: start the clock now rather than
                    # firing immediately on upgrade (beat's old timedelta schedules
                    # also waited one full interval before the first run).
                    _claim(session, spec, raw, now)
                    logger.info(
                        f"Scheduler: {spec.key} schedule started ({description})"
                    )
                    continue
                if is_due(rule, last_run, now) and _claim(session, spec, raw, now):
                    logger.info(f"Scheduler: {spec.key} is due ({description})")
                    run.append(spec.task)
        except Exception as e:  # one broken job must not stop the others
            logger.error(
                f"Scheduler: failed to evaluate {spec.key}: {e}", exc_info=True
            )
    return run
