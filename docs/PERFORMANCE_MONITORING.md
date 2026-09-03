# Performance Guide

## Overview

This is the single reference for MVidarr's performance work: the built-in monitoring API, how to instrument new code, and the optimization patterns the codebase already relies on (or should, when you're adding something new).

This file consolidates what used to be four separate documents (`PERFORMANCE_OPTIMIZATION.md`, `PERFORMANCE_OPTIMIZATION_ANALYSIS.md`, `PERFORMANCE_REGRESSION_PREVENTION.md`, `PERFORMANCE_MONITORING.md`), which had drifted out of sync with each other and with the current FastAPI codebase (stale endpoint paths, decorator examples pointing at code that no longer exists, and a lot of point-in-time "Issue #68" project narrative that had no lasting reference value). The content below has been checked against the current source rather than carried forward as-is.

## Performance Targets

Rough guidelines, not hard SLAs — this is a self-hosted app, not a service with paying customers waiting on a dashboard:

| Area | Target |
|---|---|
| Main page load | < 2s |
| Typical API endpoint | < 500ms |
| Video listing (1000+ videos) | < 1s |
| Search | < 1s |
| Download initialization | < 5s |
| Memory (5000+ video library) | < 1GB |
| DB query (common case) | < 100ms |

## Monitoring API

Live performance metrics are served from `src/api/fastapi/performance.py` under the `/api/performance` prefix. Like every other MVidarr endpoint, these require an authenticated session (see `CLAUDE.md` § API Development & Testing) — test them through the browser/UI session, not bare `curl`.

| Endpoint | Method | Auth | Returns |
|---|---|---|---|
| `/api/performance/` | GET | admin | Full overview: system + API + cache metrics, overall status |
| `/api/performance/system` | GET | admin | CPU, memory, disk, load average (via `psutil`) |
| `/api/performance/cache` | GET | any authenticated user | Cache hit/miss counts and hit rate (`MediaCacheManager`) |
| `/api/performance/endpoints` | GET | any authenticated user | Per-endpoint stats (`?limit=`, default 20, max 100) |
| `/api/performance/trends` | GET | any authenticated user | Trend data over `?hours=` (default 24, max 168) |
| `/api/performance/cache/clear` | POST | admin | Clears API/function/performance cache patterns |
| `/api/performance/health` | GET | admin | Quick status check; `warning` above 80% CPU/85% mem, `critical` above 95%/95% or cache down |

Metrics for `/`, `/endpoints`, and `/trends` are backed by `src/services/performance_monitor.py` (`get_performance_monitor()`), which is separate from the decorator described below.

## Instrumenting New Code

`src/utils/performance_monitor.py` provides a `@monitor_performance(name)` decorator that records timing into an in-process, thread-safe rolling window (last 100 calls per name). It's currently applied at the **service layer**, not on API route handlers — see `src/services/video_quality_service.py`, `src/services/dynamic_playlist_service.py`, `src/services/imvdb_discovery_service.py`, and `src/services/imvdb_analytics_service.py` for real examples:

```python
from src.utils.performance_monitor import monitor_performance

@monitor_performance("video_quality.analyze_video_quality")
def analyze_video_quality(self, video_id: int):
    ...
```

Use a `service_name.method_name` label so it's identifiable in logs. Warnings are logged automatically at 500ms–1s, errors above 1s (see the logger namespace `mvidarr.performance`).

## Database Performance

### Connection pool

Pool size is configuration, not a hardcoded constant — set it via `DB_POOL_SIZE` (env var) or the `db_pool_size` setting (see `src/config/config.py`), not by editing source. As a starting point for self-hosted deployments:

- Small library (< 1,000 videos): pool 5, overflow 10
- Medium (1,000–10,000): pool 10, overflow 20
- Large (10,000+): pool 20, overflow 40

### Indexing

Composite indexes matter most on the columns actually filtered/sorted together — e.g. `(artist_id, status)`, `(status, created_at)`. New migrations go through `migrations/` (see `docs/DATABASE_MIGRATIONS.md`), not by hand-editing the schema.

### Query anti-patterns to avoid

```python
# N+1: one query per artist
for artist in session.query(Artist).all():
    print(artist.videos)  # separate query each time

# Fix: eager load
artists = session.query(Artist).options(joinedload(Artist.videos)).all()
```

```python
# Unconditional JOIN + count-on-joined-table, even when the join buys nothing
query = session.query(Video).join(Artist, isouter=True)
total = query.count()

# Fix: only join when the result actually needs it (e.g. sorting by artist name)
if sort_by == "artist_name":
    query = session.query(Video).join(Artist, isouter=True)
    total = query.count()
else:
    total = session.query(Video).count()
    query = session.query(Video).options(joinedload(Video.artist))
```

```python
# OFFSET pagination degrades on large tables
videos = session.query(Video).offset(1000).limit(50).all()

# Prefer cursor-based pagination for large lists
videos = session.query(Video).filter(Video.id > last_id).limit(50).all()
```

## Frontend Performance

These are established patterns for the video/artist list views, worth reapplying whenever those pages grow new features:

- **Virtualize long lists** — render only the visible slice of a large video/artist list rather than the whole DOM.
- **Debounce search input** (~300ms) instead of firing a request per keystroke.
- **Batch DOM writes** — build a `DocumentFragment` and append once, not per-item.
- **Prefer transform/opacity transitions** over animating layout properties (`width`/`height`) to avoid layout thrash.

## Load Testing

Don't hand-roll a load test script — use what's already in the repo:

- `src/testing/load_testing_framework.py` — async load/stress testing against the running FastAPI app
- `src/utils/performance_testing.py` — request-based validation tooling

## Performance Checklist (for new endpoints/features)

- [ ] Queries avoid N+1 (eager-load relationships you'll actually access)
- [ ] Joins are conditional on what the request actually needs
- [ ] List endpoints paginate; large tables avoid `OFFSET`-based pagination
- [ ] New indexes added via a `migrations/` migration if a new filter/sort path needs one
- [ ] Anything non-trivial gets a `@monitor_performance` label
- [ ] Checked against `/api/performance/endpoints` after deploying, not just assumed fast

## Related Documentation

- **System Monitoring**: `MONITORING.md`
- **Architecture**: `ARCHITECTURE.md`
- **Database Migrations**: `DATABASE_MIGRATIONS.md`
- **Configuration**: `CONFIGURATION_GUIDE.md`
- **Troubleshooting**: `TROUBLESHOOTING.md`
