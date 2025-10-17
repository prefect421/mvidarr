"""
Export Service - Operations Module
Export lifecycle management and orchestration functions
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from src.database.connection import get_db
from src.database.import_export_models import (
    ExportOperation,
    ExportOptions,
    ProcessingProgress,
    ProcessingStatus,
)
from src.services.export_formatters import generate_export_file
from src.services.export_utils import (
    calculate_file_checksum,
    collect_export_data,
    count_exportable_records,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.export.operations")


def perform_export(
    operation_id: int,
    export_options: ExportOptions,
    temp_dir: Path,
    progress_callback: Optional[callable] = None,
):
    """Perform the actual export operation"""

    def update_progress(progress: ProcessingProgress):
        """Update operation progress in database"""
        try:
            with get_db() as db:
                operation = (
                    db.query(ExportOperation)
                    .filter(ExportOperation.id == operation_id)
                    .first()
                )
                if operation:
                    operation.progress_percentage = int(progress.overall_progress)
                    operation.processed_records = progress.records_processed
                    operation.total_records = progress.total_records
                    if progress.overall_progress == 100.0:
                        operation.status = ProcessingStatus.COMPLETED
                        operation.completed_at = datetime.utcnow()
                    elif operation.status == ProcessingStatus.PENDING:
                        operation.status = ProcessingStatus.RUNNING
                        operation.started_at = datetime.utcnow()
                    db.commit()

            if progress_callback:
                progress_callback(progress)

        except Exception as e:
            logger.error(f"Error updating progress for operation {operation_id}: {e}")

    try:
        logger.info(f"Starting export data collection for operation {operation_id}")

        # Initialize progress
        progress = ProcessingProgress(
            current_phase="initialization",
            total_phases=4,
            current_phase_progress=0.0,
            overall_progress=0.0,
            records_processed=0,
            total_records=0,
            records_per_second=0.0,
            status_message="Initializing export operation...",
        )
        update_progress(progress)

        # Step 1: Count total records to export
        progress.current_phase = "counting_records"
        progress.status_message = "Counting records to export..."
        progress.current_phase_progress = 10.0
        progress.overall_progress = 2.5
        update_progress(progress)

        total_counts = count_exportable_records(export_options)
        progress.total_records = sum(total_counts.values())

        # Step 2: Collect export data
        progress.current_phase = "collecting_data"
        progress.status_message = "Collecting export data..."
        progress.current_phase_progress = 0.0
        progress.overall_progress = 5.0
        update_progress(progress)

        export_data = collect_export_data(export_options, progress, update_progress)

        # Step 3: Generate output file
        progress.current_phase = "generating_file"
        progress.status_message = "Generating export file..."
        progress.current_phase_progress = 0.0
        progress.overall_progress = 80.0
        update_progress(progress)

        output_file = generate_export_file(
            operation_id, export_data, export_options, temp_dir, calculate_file_checksum
        )

        # Step 4: Finalize
        progress.current_phase = "finalizing"
        progress.status_message = "Finalizing export..."
        progress.current_phase_progress = 90.0
        progress.overall_progress = 95.0
        update_progress(progress)

        # Update operation with results
        with get_db() as db:
            operation = (
                db.query(ExportOperation)
                .filter(ExportOperation.id == operation_id)
                .first()
            )
            if operation:
                operation.output_filename = output_file.name
                operation.output_size_bytes = (
                    output_file.stat().st_size if output_file.exists() else 0
                )
                operation.output_compressed = export_options.compression_enabled
                operation.result_data = {
                    "artists_exported": len(export_data.artists),
                    "videos_exported": len(export_data.videos),
                    "playlists_exported": len(export_data.playlists),
                    "settings_exported": len(export_data.settings),
                    "blacklist_exported": len(export_data.blacklist),
                    "export_format": export_options.format.value,
                    "file_size_mb": round(
                        operation.output_size_bytes / (1024 * 1024), 2
                    ),
                }
                db.commit()

        # Complete
        progress.current_phase = "completed"
        progress.status_message = f"Export completed successfully - {output_file.name}"
        progress.current_phase_progress = 100.0
        progress.overall_progress = 100.0
        update_progress(progress)

        logger.info(f"Export operation {operation_id} completed successfully")

    except Exception as e:
        logger.error(f"Export operation {operation_id} failed: {e}")

        # Update operation status to failed
        with get_db() as db:
            operation = (
                db.query(ExportOperation)
                .filter(ExportOperation.id == operation_id)
                .first()
            )
            if operation:
                operation.status = ProcessingStatus.FAILED
                operation.error_log = [str(e)]
                operation.completed_at = datetime.utcnow()
                db.commit()

        # Update progress with failure
        if "progress" in locals():
            progress.status_message = f"Export failed: {str(e)}"
            update_progress(progress)

        raise
