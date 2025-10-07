"""
Download Processor Task
Periodic task to process pending downloads from ytdlp_service
"""

from datetime import timedelta

from src.jobs.celery_app import celery_app
from src.utils.logger import get_logger

logger = get_logger("mvidarr.jobs.download_processor")


@celery_app.task(bind=True, name="download_processor.process_downloads")
def process_pending_downloads_task(self):
    """
    Periodic task to process pending downloads
    This ensures downloads are processed even if the automatic trigger fails
    """
    try:
        from src.services.ytdlp_service import ytdlp_service

        logger.info("Processing pending downloads via Celery task")
        result = ytdlp_service.process_pending_downloads()

        logger.info(f"Download processing result: {result}")
        return result

    except Exception as e:
        logger.error(f"Error processing downloads in Celery task: {e}")
        return {"success": False, "error": str(e)}


# Note: Beat schedule is now configured in celery_app.py to avoid conflicts
