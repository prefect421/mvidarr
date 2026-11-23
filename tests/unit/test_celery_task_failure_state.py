"""#609: batch enrichment needs CallbackTask; FAILURE must not be stored by hand."""

import pathlib
import re


def test_batch_enrich_task_has_update_progress():
    from src.jobs.metadata_tasks import batch_enrich_artists_task

    assert hasattr(batch_enrich_artists_task, "update_progress")


def test_no_task_hand_stores_failure_state():
    # A hand-written FAILURE meta lacks 'exc_type', so Celery raises
    # KeyError/ValueError when it later reads the result back.
    offenders = []
    for path in pathlib.Path("src").rglob("*.py"):
        if re.search(r'state\s*=\s*"FAILURE"', path.read_text()):
            offenders.append(str(path))
    assert offenders == []
