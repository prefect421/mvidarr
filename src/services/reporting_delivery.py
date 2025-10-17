"""
Real-Time Reporting System - Report Delivery
Functions for delivering reports via different channels
"""

from src.services.reporting_models import GeneratedReport
from src.utils.logger import get_logger

logger = get_logger("mvidarr.reporting_delivery")


async def deliver_report(report: GeneratedReport, enable_webhook_delivery: bool = True):
    """Deliver report via configured channels"""
    try:
        config = report.config

        # Webhook delivery
        if config.webhook_urls and enable_webhook_delivery:
            await deliver_via_webhook(report)

        # Email delivery would be implemented here
        # File system delivery would be implemented here

    except Exception as e:
        logger.error(f"Report delivery failed: {e}")


async def deliver_via_webhook(report: GeneratedReport):
    """Deliver report via webhook"""
    try:
        import aiohttp

        payload = {
            "report_id": report.report_id,
            "title": report.config.title,
            "type": report.config.report_type.value,
            "generated_at": report.generation_time,
            "data": report.data,
            "insights": report.insights,
            "recommendations": report.recommendations,
        }

        async with aiohttp.ClientSession() as session:
            for webhook_url in report.config.webhook_urls:
                try:
                    async with session.post(
                        webhook_url, json=payload, timeout=10
                    ) as response:
                        if response.status == 200:
                            logger.info(
                                f"📊 Report delivered to webhook: {webhook_url}"
                            )
                        else:
                            logger.warning(
                                f"Webhook delivery failed: {webhook_url} - Status {response.status}"
                            )
                except Exception as e:
                    logger.error(f"Webhook delivery error for {webhook_url}: {e}")

    except Exception as e:
        logger.error(f"Webhook delivery failed: {e}")
