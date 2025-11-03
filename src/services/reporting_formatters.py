"""
Real-Time Reporting System - Report Formatters
Functions for formatting reports in different output formats
"""

import csv
import io
import json
import tempfile
from datetime import datetime
from typing import Any, Dict

from src.services.reporting_models import GeneratedReport, ReportFormat
from src.utils.logger import get_logger

logger = get_logger("mvidarr.reporting_formatters")


async def format_report(report: GeneratedReport):
    """Format report in specified output format"""
    try:
        config = report.config

        if config.format == ReportFormat.HTML:
            report.file_path = await generate_html_report(report)
        elif config.format == ReportFormat.PDF:
            report.file_path = await generate_pdf_report(report)
        elif config.format == ReportFormat.CSV:
            report.file_path = await generate_csv_report(report)
        elif config.format == ReportFormat.DASHBOARD:
            report.dashboard_url = await generate_dashboard_url(report)

    except Exception as e:
        logger.error(f"Report formatting failed: {e}")


async def generate_html_report(report: GeneratedReport) -> str:
    """Generate HTML format report"""
    try:
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{report.config.title}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; }}
                .header {{ background-color: #f8f9fa; padding: 20px; border-radius: 5px; }}
                .section {{ margin: 20px 0; padding: 15px; border-left: 3px solid #007bff; }}
                .metric {{ display: inline-block; margin: 10px; padding: 10px; background: #e9ecef; border-radius: 3px; }}
                .chart {{ margin: 20px 0; text-align: center; }}
                .insight {{ background: #d4edda; padding: 10px; margin: 5px 0; border-radius: 3px; }}
                .recommendation {{ background: #f8d7da; padding: 10px; margin: 5px 0; border-radius: 3px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>{report.config.title}</h1>
                <p>{report.config.description}</p>
                <p>Generated: {datetime.fromtimestamp(report.generation_time).strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p>Processing Time: {report.processing_time_seconds:.2f} seconds</p>
            </div>

            <div class="section">
                <h2>Report Data</h2>
                <pre>{json.dumps(report.data, indent=2, default=str)}</pre>
            </div>

            {f'''<div class="section">
                <h2>Insights</h2>
                {''.join(f'<div class="insight">{insight}</div>' for insight in report.insights)}
            </div>''' if report.insights else ''}

            {f'''<div class="section">
                <h2>Recommendations</h2>
                {''.join(f'<div class="recommendation">{rec}</div>' for rec in report.recommendations)}
            </div>''' if report.recommendations else ''}
        </body>
        </html>
        """

        # Save to temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            f.write(html_content)
            return f.name

    except Exception as e:
        logger.error(f"HTML report generation failed: {e}")
        return ""


async def generate_pdf_report(report: GeneratedReport) -> str:
    """Generate PDF format report (placeholder - would need additional libraries)"""
    # This would require libraries like reportlab or weasyprint
    logger.info("PDF report generation not implemented - returning HTML")
    return await generate_html_report(report)


async def generate_csv_report(report: GeneratedReport) -> str:
    """Generate CSV format report"""
    try:
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(["Report", report.config.title])
        writer.writerow(
            [
                "Generated",
                datetime.fromtimestamp(report.generation_time).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
            ]
        )
        writer.writerow(
            ["Processing Time", f"{report.processing_time_seconds:.2f} seconds"]
        )
        writer.writerow([])

        # Write data (flatten JSON structure)
        def write_dict(data, prefix=""):
            for key, value in data.items():
                if isinstance(value, dict):
                    write_dict(value, f"{prefix}{key}.")
                elif isinstance(value, list):
                    writer.writerow([f"{prefix}{key}", f"List with {len(value)} items"])
                else:
                    writer.writerow([f"{prefix}{key}", str(value)])

        writer.writerow(["Key", "Value"])
        write_dict(report.data)

        # Save to temporary file
        csv_content = output.getvalue()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            return f.name

    except Exception as e:
        logger.error(f"CSV report generation failed: {e}")
        return ""


async def generate_dashboard_url(report: GeneratedReport) -> str:
    """Generate dashboard URL for report"""
    # This would integrate with your web dashboard
    base_url = "http://localhost:5000/dashboard"
    return f"{base_url}/reports/{report.report_id}"
