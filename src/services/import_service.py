"""
Enhanced Import Service for MVidarr - Refactored
Multi-format data import system with validation and progress tracking

Refactored from monolithic 2,163-line file into modular architecture:
- import_parsers: File parsing functions for JSON, YAML, XML, CSV formats
- import_validators: Validation functions for data integrity
- import_operations: Import/CRUD operations for artists, videos, playlists, settings
- import_service: Main service aggregator (this file)

Original file: 2,163 lines with 40+ methods
Refactored into: 4 specialized modules for better maintainability
"""

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import and_

from src.database.connection import get_db
from src.database.import_export_models import (
    ImportOperation,
    ImportOptions,
    ProcessingProgress,
    ProcessingStatus,
    ValidationError,
    ValidationLevel,
    ValidationResult,
)
from src.services.import_operations import perform_import
from src.services.import_parsers import parse_import_file
from src.services.import_validators import validate_import_data
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.import_service")


class ImportService:
    """Service for importing data from various formats"""

    def __init__(self):
        """Initialize the ImportService with default configurations"""
        # File patterns and limits
        self.allowed_extensions = [".json", ".yaml", ".yml", ".xml", ".zip", ".gz"]
        self.max_file_size_mb = 100
        self.max_filename_length = 255

        # Temporary directory for file processing
        self.temp_dir = Path("/tmp/mvidarr_imports")
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def start_import(
        self,
        source_file_path: Path,
        import_options: ImportOptions,
        user_id: int,
        progress_callback: Optional[callable] = None,
    ) -> int:
        """Start an import operation

        Args:
            source_file_path: Path to the import file
            import_options: Options for import operation
            user_id: ID of the user starting the import
            progress_callback: Optional callback for progress updates

        Returns:
            Operation ID for tracking the import
        """
        try:
            # Validate file exists
            if not source_file_path.exists():
                raise FileNotFoundError(f"Import file not found: {source_file_path}")

            # Validate file extension
            if source_file_path.suffix.lower() not in self.allowed_extensions:
                raise ValueError(f"Unsupported file format: {source_file_path.suffix}")

            # Validate file size
            file_size_mb = os.path.getsize(source_file_path) / (1024 * 1024)
            if file_size_mb > self.max_file_size_mb:
                raise ValueError(
                    f"File too large: {file_size_mb:.1f} MB (max: {self.max_file_size_mb} MB)"
                )

            # Create import operation record
            with get_db() as db:
                operation = ImportOperation(
                    user_id=user_id,
                    filename=source_file_path.name,
                    file_path=str(source_file_path),
                    file_size_bytes=os.path.getsize(source_file_path),
                    import_mode=import_options.mode,
                    import_options=self._serialize_import_options(import_options),
                    status=ProcessingStatus.PENDING,
                    created_at=datetime.utcnow(),
                )
                db.add(operation)
                db.commit()
                db.refresh(operation)
                operation_id = operation.id

            logger.info(
                f"Created import operation {operation_id} for file {source_file_path}"
            )

            # Start import in background thread
            import_thread = threading.Thread(
                target=self._perform_import,
                args=(
                    operation_id,
                    source_file_path,
                    import_options,
                    progress_callback,
                ),
                daemon=True,
            )
            import_thread.start()

            return operation_id

        except Exception as e:
            logger.error(f"Error starting import operation: {e}")
            raise

    def validate_import_file(
        self, source_file_path: Path, validation_level: ValidationLevel
    ) -> ValidationResult:
        """Validate an import file without importing

        Args:
            source_file_path: Path to the import file
            validation_level: Level of validation strictness

        Returns:
            ValidationResult with detailed validation information
        """
        start_time = datetime.utcnow()

        try:
            # Parse the import file
            import_data = parse_import_file(source_file_path)

            # Validate the data
            validation_result = validate_import_data(import_data, validation_level)

            # Calculate processing time
            end_time = datetime.utcnow()
            validation_result.processing_time = (end_time - start_time).total_seconds()

            return validation_result

        except Exception as e:
            logger.error(f"Error validating import file {source_file_path}: {e}")
            return ValidationResult(
                is_valid=False,
                total_records=0,
                valid_records=0,
                invalid_records=0,
                warnings_count=0,
                errors=[
                    ValidationError(
                        record_type="file",
                        record_id=None,
                        field_name="parsing",
                        error_code="PARSE_ERROR",
                        error_message=str(e),
                        severity="error",
                    )
                ],
                processing_time=(datetime.utcnow() - start_time).total_seconds(),
            )

    def get_import_status(self, operation_id: int) -> Optional[Dict[str, Any]]:
        """Get the current status of an import operation

        Args:
            operation_id: ID of the import operation

        Returns:
            Dictionary with operation status, or None if not found
        """
        try:
            with get_db() as db:
                operation = (
                    db.query(ImportOperation)
                    .filter(ImportOperation.id == operation_id)
                    .first()
                )
                if not operation:
                    return None
                return operation.to_dict()
        except Exception as e:
            logger.error(
                f"Error getting import status for operation {operation_id}: {e}"
            )
            return None

    def cancel_import(self, operation_id: int, user_id: int) -> bool:
        """Cancel a running import operation

        Args:
            operation_id: ID of the import operation
            user_id: ID of the user requesting cancellation

        Returns:
            True if cancelled successfully, False otherwise
        """
        try:
            with get_db() as db:
                operation = (
                    db.query(ImportOperation)
                    .filter(
                        and_(
                            ImportOperation.id == operation_id,
                            ImportOperation.user_id == user_id,
                            ImportOperation.status.in_(
                                [ProcessingStatus.PENDING, ProcessingStatus.RUNNING]
                            ),
                        )
                    )
                    .first()
                )

                if not operation:
                    return False

                operation.status = ProcessingStatus.CANCELLED
                operation.completed_at = datetime.utcnow()
                db.commit()

                logger.info(f"Cancelled import operation {operation_id}")
                return True

        except Exception as e:
            logger.error(f"Error cancelling import operation {operation_id}: {e}")
            return False

    def _perform_import(
        self,
        operation_id: int,
        source_file_path: Path,
        import_options: ImportOptions,
        progress_callback: Optional[callable] = None,
    ):
        """Perform the actual import operation (delegates to import_operations module)

        Args:
            operation_id: ID of the import operation
            source_file_path: Path to the import file
            import_options: Options for import operation
            progress_callback: Optional callback for progress updates
        """

        def update_progress(progress: ProcessingProgress):
            """Update operation progress in database"""
            try:
                with get_db() as db:
                    operation = (
                        db.query(ImportOperation)
                        .filter(ImportOperation.id == operation_id)
                        .first()
                    )
                    if operation:
                        operation.progress_percentage = int(progress.overall_progress)
                        operation.processed_records = progress.records_processed
                        operation.total_records = progress.total_records
                        operation.successful_records = (
                            progress.records_processed - progress.errors_count
                        )
                        operation.failed_records = progress.errors_count

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
                logger.error(
                    f"Error updating progress for import operation {operation_id}: {e}"
                )

        try:
            logger.info(f"Starting import processing for operation {operation_id}")

            # Initialize progress
            progress = ProcessingProgress(
                current_phase="initialization",
                total_phases=5,
                current_phase_progress=0.0,
                overall_progress=0.0,
                records_processed=0,
                total_records=0,
                records_per_second=0.0,
                status_message="Initializing import operation...",
            )
            update_progress(progress)

            # Step 1: Parse import file
            progress.current_phase = "parsing"
            progress.status_message = "Parsing import file..."
            progress.current_phase_progress = 10.0
            progress.overall_progress = 2.0
            update_progress(progress)

            import_data = parse_import_file(source_file_path)

            # Step 2: Validate data
            progress.current_phase = "validation"
            progress.status_message = "Validating import data..."
            progress.current_phase_progress = 0.0
            progress.overall_progress = 5.0
            update_progress(progress)

            validation_result = validate_import_data(
                import_data, import_options.validation_level
            )

            # Store validation results
            with get_db() as db:
                operation = (
                    db.query(ImportOperation)
                    .filter(ImportOperation.id == operation_id)
                    .first()
                )
                if operation:
                    operation.validation_data = {
                        "is_valid": validation_result.is_valid,
                        "total_records": validation_result.total_records,
                        "valid_records": validation_result.valid_records,
                        "invalid_records": validation_result.invalid_records,
                        "warnings_count": validation_result.warnings_count,
                        "errors_count": len(validation_result.errors),
                    }
                    db.commit()

            # Check if validation failed critically
            if (
                not validation_result.is_valid
                and import_options.validation_level == ValidationLevel.STRICT
            ):
                raise ValueError(
                    f"Validation failed with {len(validation_result.errors)} errors"
                )

            progress.total_records = validation_result.total_records
            progress.warnings_count = validation_result.warnings_count
            progress.errors_count = len(validation_result.errors)

            # Step 3-5: Delegate to perform_import function from import_operations module
            progress.current_phase = "importing"
            progress.status_message = "Importing data..."
            progress.current_phase_progress = 0.0
            progress.overall_progress = 25.0
            update_progress(progress)

            # Delegate to import_operations module
            import_results = perform_import(
                operation_id, import_data, import_options, progress, update_progress
            )

            # Finalize
            progress.current_phase = "finalizing"
            progress.status_message = "Finalizing import..."
            progress.current_phase_progress = 90.0
            progress.overall_progress = 95.0
            update_progress(progress)

            # Store final results
            with get_db() as db:
                operation = (
                    db.query(ImportOperation)
                    .filter(ImportOperation.id == operation_id)
                    .first()
                )
                if operation:
                    operation.import_results = import_results
                    operation.status = ProcessingStatus.COMPLETED
                    operation.completed_at = datetime.utcnow()
                    db.commit()

            progress.overall_progress = 100.0
            progress.status_message = "Import completed successfully"
            update_progress(progress)

            logger.info(f"Import operation {operation_id} completed successfully")

        except Exception as e:
            logger.error(f"Error performing import operation {operation_id}: {e}")

            # Update operation with error
            with get_db() as db:
                operation = (
                    db.query(ImportOperation)
                    .filter(ImportOperation.id == operation_id)
                    .first()
                )
                if operation:
                    operation.status = ProcessingStatus.FAILED
                    operation.error_log = [str(e)]
                    operation.completed_at = datetime.utcnow()
                    db.commit()

            # Update progress with failure
            if "progress" in locals():
                progress.status_message = f"Import failed: {str(e)}"
                update_progress(progress)

            raise

    def _serialize_import_options(
        self, import_options: ImportOptions
    ) -> Dict[str, Any]:
        """Serialize import options for database storage

        Args:
            import_options: ImportOptions object to serialize

        Returns:
            Dictionary with serialized import options
        """
        return {
            "mode": import_options.mode.value,
            "validation_level": import_options.validation_level.value,
            "overwrite_duplicates": import_options.overwrite_duplicates,
            "update_existing": import_options.update_existing,
            "skip_invalid_records": import_options.skip_invalid_records,
            "create_missing_artists": import_options.create_missing_artists,
            "preserve_ids": import_options.preserve_ids,
            "sanitize_file_paths": import_options.sanitize_file_paths,
            "validate_external_ids": import_options.validate_external_ids,
            "batch_size": import_options.batch_size,
            "max_errors": import_options.max_errors,
            "backup_before_import": import_options.backup_before_import,
            "dry_run": import_options.dry_run,
        }


# Global instance
import_service = ImportService()
