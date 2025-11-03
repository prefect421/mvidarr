"""
Bulk Operations Service for MVidarr 0.9.7 - Issue #74
Handles bulk operations with background processing, progress tracking, and undo/redo functionality.
"""

import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from src.database.bulk_models import (
    BulkOperation,
    BulkOperationAudit,
    BulkOperationProgress,
    BulkOperationStatus,
    BulkOperationType,
)
from src.database.connection import get_db
from src.database.models import Artist, Video, VideoStatus
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.bulk_operations")


class BulkOperationProcessor:
    """Background processor for bulk operations"""

    def __init__(self):
        self.active_operations: Dict[int, threading.Thread] = {}
        self.chunk_size = 50  # Process items in chunks
        self.max_concurrent_operations = 3

    def submit_operation(self, operation_id: int) -> bool:
        """Submit a bulk operation for background processing"""
        if len(self.active_operations) >= self.max_concurrent_operations:
            logger.warning(
                f"Maximum concurrent operations reached, queuing operation {operation_id}"
            )
            return False

        if operation_id in self.active_operations:
            logger.warning(f"Operation {operation_id} is already running")
            return False

        # Start background thread
        thread = threading.Thread(
            target=self._process_operation,
            args=(operation_id,),
            name=f"BulkOperation-{operation_id}",
        )
        thread.daemon = True
        thread.start()

        self.active_operations[operation_id] = thread
        logger.info(f"Started background processing for operation {operation_id}")
        return True

    def cancel_operation(self, operation_id: int) -> bool:
        """Cancel a running bulk operation"""
        try:
            with get_db() as db:
                operation = (
                    db.query(BulkOperation)
                    .filter(BulkOperation.id == operation_id)
                    .first()
                )
                if not operation:
                    return False

                operation.status = BulkOperationStatus.CANCELLED
                operation.completed_at = datetime.utcnow()
                db.commit()

                # Remove from active operations
                if operation_id in self.active_operations:
                    del self.active_operations[operation_id]

                logger.info(f"Cancelled operation {operation_id}")
                return True
        except Exception as e:
            logger.error(f"Error cancelling operation {operation_id}: {e}")
            return False

    def get_active_operations(self) -> List[int]:
        """Get list of currently active operation IDs"""
        return list(self.active_operations.keys())

    def _process_operation(self, operation_id: int):
        """Process a bulk operation in background"""
        try:
            with get_db() as db:
                operation = (
                    db.query(BulkOperation)
                    .filter(BulkOperation.id == operation_id)
                    .first()
                )
                if not operation:
                    logger.error(f"Operation {operation_id} not found")
                    return

                # Update status to running
                operation.status = BulkOperationStatus.RUNNING
                operation.started_at = datetime.utcnow()
                db.commit()

                # Create progress tracker
                progress = BulkOperationProgress(
                    operation_id=operation_id,
                    stage="initializing",
                    status_message="Starting bulk operation...",
                )
                db.add(progress)
                db.commit()

                # Process based on operation type
                if operation.operation_type == BulkOperationType.VIDEO_STATUS_UPDATE:
                    self._process_video_status_update(db, operation, progress)
                elif (
                    operation.operation_type == BulkOperationType.VIDEO_METADATA_UPDATE
                ):
                    self._process_video_metadata_update(db, operation, progress)
                elif operation.operation_type == BulkOperationType.VIDEO_DELETE:
                    self._process_video_delete(db, operation, progress)
                elif (
                    operation.operation_type == BulkOperationType.ARTIST_METADATA_UPDATE
                ):
                    self._process_artist_metadata_update(db, operation, progress)
                elif operation.operation_type == BulkOperationType.ARTIST_DELETE:
                    self._process_artist_delete(db, operation, progress)
                else:
                    raise ValueError(
                        f"Unsupported operation type: {operation.operation_type}"
                    )

                # Final progress update
                progress.stage = "completed"
                progress.status_message = "Operation completed successfully"
                db.commit()

        except Exception as e:
            logger.error(f"Error processing operation {operation_id}: {e}")
            self._handle_operation_error(operation_id, str(e))
        finally:
            # Clean up
            if operation_id in self.active_operations:
                del self.active_operations[operation_id]

    def _process_video_status_update(
        self, db: Session, operation: BulkOperation, progress: BulkOperationProgress
    ):
        """Process bulk video status updates"""
        target_ids = operation.target_ids
        new_status = operation.operation_params.get("new_status")

        if not new_status:
            raise ValueError("new_status parameter is required")

        try:
            new_status_enum = VideoStatus(new_status)
        except ValueError:
            raise ValueError(f"Invalid status: {new_status}")

        # Process in chunks
        total_processed = 0
        total_successful = 0
        total_failed = 0

        for i in range(0, len(target_ids), self.chunk_size):
            chunk = target_ids[i : i + self.chunk_size]

            # Update progress
            progress.stage = "processing"
            progress.current_item_id = str(chunk[0]) if chunk else None
            progress.status_message = f"Processing chunk {i // self.chunk_size + 1} of {(len(target_ids) + self.chunk_size - 1) // self.chunk_size}"

            # Calculate performance metrics
            if total_processed > 0:
                elapsed_time = (
                    datetime.utcnow() - operation.started_at
                ).total_seconds()
                progress.items_per_second = total_processed / elapsed_time
                remaining_items = len(target_ids) - total_processed
                if progress.items_per_second > 0:
                    progress.estimated_time_remaining = int(
                        remaining_items / progress.items_per_second
                    )

            db.commit()

            # Process chunk
            for video_id in chunk:
                try:
                    video = db.query(Video).filter(Video.id == video_id).first()
                    if not video:
                        operation.add_error(video_id, "Video not found")
                        total_failed += 1
                        continue

                    # Store undo data
                    if operation.is_undoable:
                        if operation.undo_data is None:
                            operation.undo_data = {}
                        operation.undo_data[str(video_id)] = {
                            "old_status": video.status.value,
                            "field": "status",
                        }

                    # Create audit entry
                    audit = BulkOperationAudit(
                        operation_id=operation.id,
                        item_type="video",
                        item_id=video_id,
                        action="update",
                        field_name="status",
                        old_value=video.status.value,
                        new_value=new_status,
                        batch_sequence=total_processed,
                    )
                    db.add(audit)

                    # Update video status
                    video.status = new_status_enum
                    total_successful += 1

                except Exception as e:
                    operation.add_error(video_id, str(e))
                    total_failed += 1
                    logger.error(f"Error updating video {video_id}: {e}")

                total_processed += 1
                operation.update_progress(
                    total_processed, total_successful, total_failed
                )

            db.commit()

            # Check for cancellation
            db.refresh(operation)
            if operation.status == BulkOperationStatus.CANCELLED:
                logger.info(f"Operation {operation.id} was cancelled")
                return

        # Final update
        operation.results = {
            "total_processed": total_processed,
            "successful": total_successful,
            "failed": total_failed,
            "new_status": new_status,
        }
        db.commit()

        logger.info(
            f"Completed video status update operation {operation.id}: {total_successful} successful, {total_failed} failed"
        )

    def _process_video_metadata_update(
        self, db: Session, operation: BulkOperation, progress: BulkOperationProgress
    ):
        """Process bulk video metadata updates"""
        target_ids = operation.target_ids
        updates = operation.operation_params.get("updates", {})

        if not updates:
            raise ValueError("updates parameter is required")

        total_processed = 0
        total_successful = 0
        total_failed = 0

        for i in range(0, len(target_ids), self.chunk_size):
            chunk = target_ids[i : i + self.chunk_size]

            progress.stage = "processing"
            progress.status_message = (
                f"Updating metadata for chunk {i // self.chunk_size + 1}"
            )
            db.commit()

            for video_id in chunk:
                try:
                    video = db.query(Video).filter(Video.id == video_id).first()
                    if not video:
                        operation.add_error(video_id, "Video not found")
                        total_failed += 1
                        continue

                    # Store undo data and apply updates
                    if operation.undo_data is None:
                        operation.undo_data = {}
                    operation.undo_data[str(video_id)] = {}

                    for field, new_value in updates.items():
                        if hasattr(video, field):
                            old_value = getattr(video, field)
                            operation.undo_data[str(video_id)][field] = old_value

                            # Create audit entry
                            audit = BulkOperationAudit(
                                operation_id=operation.id,
                                item_type="video",
                                item_id=video_id,
                                action="update",
                                field_name=field,
                                old_value=old_value,
                                new_value=new_value,
                                batch_sequence=total_processed,
                            )
                            db.add(audit)

                            setattr(video, field, new_value)

                    total_successful += 1

                except Exception as e:
                    operation.add_error(video_id, str(e))
                    total_failed += 1
                    logger.error(f"Error updating video metadata {video_id}: {e}")

                total_processed += 1
                operation.update_progress(
                    total_processed, total_successful, total_failed
                )

            db.commit()

            if operation.status == BulkOperationStatus.CANCELLED:
                return

        operation.results = {
            "total_processed": total_processed,
            "successful": total_successful,
            "failed": total_failed,
            "updated_fields": list(updates.keys()),
        }
        db.commit()

    def _process_video_delete(
        self, db: Session, operation: BulkOperation, progress: BulkOperationProgress
    ):
        """Process bulk video deletion"""
        target_ids = operation.target_ids

        total_processed = 0
        total_successful = 0
        total_failed = 0

        for i in range(0, len(target_ids), self.chunk_size):
            chunk = target_ids[i : i + self.chunk_size]

            progress.stage = "processing"
            progress.status_message = (
                f"Deleting videos in chunk {i // self.chunk_size + 1}"
            )
            db.commit()

            for video_id in chunk:
                try:
                    video = db.query(Video).filter(Video.id == video_id).first()
                    if not video:
                        operation.add_error(video_id, "Video not found")
                        total_failed += 1
                        continue

                    # Store complete video data for undo
                    if operation.is_undoable:
                        if operation.undo_data is None:
                            operation.undo_data = {}
                        operation.undo_data[str(video_id)] = {
                            "title": video.title,
                            "artist_id": video.artist_id,
                            "status": video.status.value,
                            "quality": video.quality,
                            "year": video.year,
                            "duration": video.duration,
                            # Add other important fields for restoration
                        }

                    # Create audit entry
                    audit = BulkOperationAudit(
                        operation_id=operation.id,
                        item_type="video",
                        item_id=video_id,
                        action="delete",
                        old_value={"title": video.title, "artist_id": video.artist_id},
                        batch_sequence=total_processed,
                    )
                    db.add(audit)

                    # Delete video
                    db.delete(video)
                    total_successful += 1

                except Exception as e:
                    operation.add_error(video_id, str(e))
                    total_failed += 1
                    logger.error(f"Error deleting video {video_id}: {e}")

                total_processed += 1
                operation.update_progress(
                    total_processed, total_successful, total_failed
                )

            db.commit()

            if operation.status == BulkOperationStatus.CANCELLED:
                return

        operation.results = {
            "total_processed": total_processed,
            "successful": total_successful,
            "failed": total_failed,
            "action": "delete",
        }
        db.commit()

    def _process_artist_metadata_update(
        self, db: Session, operation: BulkOperation, progress: BulkOperationProgress
    ):
        """Process bulk artist metadata updates"""
        from src.database.models import Artist

        try:
            target_ids = operation.target_ids
            operation_params = operation.operation_params
            action = operation_params.get("action", "metadata_update")

            progress.stage = "processing"
            progress.status_message = f"Processing {len(target_ids)} artists..."
            db.commit()

            successful_count = 0
            failed_count = 0

            for i, artist_id in enumerate(target_ids):
                try:
                    artist = db.query(Artist).filter(Artist.id == artist_id).first()
                    if not artist:
                        failed_count += 1
                        continue

                    if action == "metadata_update":
                        # Handle metadata updates (like genre additions)
                        metadata = operation_params.get("metadata", {})

                        # Update artist fields based on metadata
                        for field, value in metadata.items():
                            if hasattr(artist, field):
                                if field == "genres" and value:
                                    # Handle genres addition/update - frontend sends genres array
                                    if isinstance(value, list):
                                        # Handle array of genres from frontend
                                        current_genres = artist.genres or ""
                                        new_genres = []
                                        if current_genres:
                                            new_genres.extend(
                                                [
                                                    g.strip()
                                                    for g in current_genres.split(",")
                                                ]
                                            )

                                        for genre in value:
                                            if (
                                                genre.strip()
                                                and genre.strip() not in new_genres
                                            ):
                                                new_genres.append(genre.strip())

                                        artist.genres = ", ".join(new_genres)
                                    else:
                                        # Handle single genre string
                                        current_genres = artist.genres or ""
                                        if value not in current_genres:
                                            if current_genres:
                                                artist.genres = (
                                                    f"{current_genres}, {value}"
                                                )
                                            else:
                                                artist.genres = value
                                elif field == "biography" and value:
                                    artist.biography = value
                                elif field == "formed_year" and value:
                                    artist.formed_year = value
                                elif field == "country" and value:
                                    artist.country = value
                                # Add other fields as needed

                    elif action == "validate_metadata":
                        # Validate artist metadata
                        validation_issues = []
                        if not artist.genres:
                            validation_issues.append("Missing genre")
                        if not artist.biography:
                            validation_issues.append("Missing biography")

                        # Log validation results
                        if validation_issues:
                            logger.info(
                                f"Artist {artist.name} has issues: {', '.join(validation_issues)}"
                            )

                    elif action == "refresh_metadata":
                        # Refresh metadata from external sources
                        # This could integrate with IMVDB or other services
                        pass

                    successful_count += 1

                    # Create audit record
                    audit = BulkOperationAudit(
                        operation_id=operation.id,
                        item_type="artist",
                        item_id=artist_id,
                        action=action,
                        field_name="metadata",
                        old_value=str(metadata) if action == "metadata_update" else "",
                        new_value=(
                            str(metadata)
                            if action == "metadata_update"
                            else "validated"
                        ),
                        batch_sequence=i + 1,
                    )
                    db.add(audit)

                except Exception as e:
                    failed_count += 1
                    logger.error(f"Error processing artist {artist_id}: {str(e)}")

                # Update progress
                processed = i + 1
                progress.current_item_id = artist_id
                progress.stage_progress = (processed / len(target_ids)) * 100
                progress.status_message = (
                    f"Processed {processed}/{len(target_ids)} artists"
                )

                operation.processed_items = processed
                operation.successful_items = successful_count
                operation.failed_items = failed_count
                operation.progress_percentage = (processed / len(target_ids)) * 100

                if processed % 10 == 0:  # Commit every 10 items
                    db.commit()

            # Final commit
            db.commit()

            # Update operation status
            operation.status = BulkOperationStatus.COMPLETED
            operation.completed_at = datetime.utcnow()
            db.commit()

            logger.info(
                f"Completed artist metadata update: {successful_count} successful, {failed_count} failed"
            )

        except Exception as e:
            logger.error(f"Error in artist metadata update: {str(e)}")
            operation.status = BulkOperationStatus.FAILED
            operation.completed_at = datetime.utcnow()
            if operation.error_log:
                operation.error_log.append(str(e))
            else:
                operation.error_log = [str(e)]
            db.commit()
            raise

    def _process_artist_delete(
        self, db: Session, operation: BulkOperation, progress: BulkOperationProgress
    ):
        """Process bulk artist deletion"""
        # Similar implementation to video delete
        # This is a placeholder - implement based on specific requirements
        pass

    def _handle_operation_error(self, operation_id: int, error_message: str):
        """Handle operation error and update status"""
        try:
            with get_db() as db:
                operation = (
                    db.query(BulkOperation)
                    .filter(BulkOperation.id == operation_id)
                    .first()
                )
                if operation:
                    operation.status = BulkOperationStatus.FAILED
                    operation.completed_at = datetime.utcnow()
                    operation.add_error("operation", error_message)
                    db.commit()
        except Exception as e:
            logger.error(f"Error updating failed operation {operation_id}: {e}")


class BulkOperationsService:
    """Service for managing bulk operations"""

    def __init__(self):
        self.processor = BulkOperationProcessor()

    def create_operation(
        self,
        user_id: int,
        operation_type: BulkOperationType,
        operation_name: str,
        target_ids: List[int],
        operation_params: Dict[str, Any] = None,
        description: str = None,
        is_preview: bool = False,
    ) -> BulkOperation:
        """Create a new bulk operation"""
        try:
            with get_db() as db:
                operation = BulkOperation(
                    user_id=user_id,
                    operation_type=operation_type,
                    operation_name=operation_name,
                    description=description,
                    target_ids=target_ids,
                    operation_params=operation_params or {},
                    total_items=len(target_ids),
                    is_preview=is_preview,
                )

                db.add(operation)
                db.commit()
                db.refresh(operation)

                # Store the ID before the session closes
                operation_id = operation.id

                logger.info(f"Created bulk operation {operation_id}: {operation_name}")

                # Return a fresh copy from a new session to avoid session binding issues
                with get_db() as fresh_db:
                    fresh_operation = (
                        fresh_db.query(BulkOperation)
                        .filter(BulkOperation.id == operation_id)
                        .first()
                    )
                    if fresh_operation:
                        # Make the object independent of the session
                        fresh_db.expunge(fresh_operation)
                        return fresh_operation
                    else:
                        raise Exception(
                            f"Failed to retrieve created operation {operation_id}"
                        )

        except Exception as e:
            logger.error(f"Error creating bulk operation: {e}")
            raise

    def start_operation(self, operation_id: int) -> bool:
        """Start a bulk operation"""
        try:
            with get_db() as db:
                operation = (
                    db.query(BulkOperation)
                    .filter(BulkOperation.id == operation_id)
                    .first()
                )
                if not operation:
                    return False

                if operation.is_preview:
                    # Process preview synchronously
                    self._process_preview(db, operation)
                    return True
                else:
                    # Submit for background processing
                    return self.processor.submit_operation(operation_id)

        except Exception as e:
            logger.error(f"Error starting operation {operation_id}: {e}")
            return False

    def cancel_operation(self, operation_id: int) -> bool:
        """Cancel a running operation"""
        return self.processor.cancel_operation(operation_id)

    def get_operation(
        self, operation_id: int, include_sensitive: bool = False
    ) -> Optional[BulkOperation]:
        """Get operation by ID"""
        try:
            with get_db() as db:
                return (
                    db.query(BulkOperation)
                    .filter(BulkOperation.id == operation_id)
                    .first()
                )
        except Exception as e:
            logger.error(f"Error getting operation {operation_id}: {e}")
            return None

    def get_user_operations(
        self, user_id: int, limit: int = 50, status: BulkOperationStatus = None
    ) -> List[BulkOperation]:
        """Get operations for a user"""
        try:
            with get_db() as db:
                query = db.query(BulkOperation).filter(BulkOperation.user_id == user_id)

                if status:
                    query = query.filter(BulkOperation.status == status)

                return (
                    query.order_by(BulkOperation.created_at.desc()).limit(limit).all()
                )

        except Exception as e:
            logger.error(f"Error getting user operations: {e}")
            return []

    def undo_operation(self, operation_id: int, user_id: int) -> bool:
        """Undo a completed operation"""
        try:
            with get_db() as db:
                operation = (
                    db.query(BulkOperation)
                    .filter(
                        and_(
                            BulkOperation.id == operation_id,
                            BulkOperation.user_id == user_id,
                        )
                    )
                    .first()
                )

                if not operation or not operation.can_undo():
                    return False

                # Create undo operation
                undo_operation = self._create_undo_operation(db, operation, user_id)

                # Start undo processing
                if self.processor.submit_operation(undo_operation.id):
                    operation.undone_at = datetime.utcnow()
                    operation.undone_by = user_id
                    db.commit()
                    return True

                return False

        except Exception as e:
            logger.error(f"Error undoing operation {operation_id}: {e}")
            return False

    def _process_preview(self, db: Session, operation: BulkOperation):
        """Process operation in preview mode"""
        # Implement preview logic - validate changes without applying them
        # This is a simplified implementation
        operation.status = BulkOperationStatus.COMPLETED
        operation.preview_results = {
            "would_affect": len(operation.target_ids),
            "preview_mode": True,
            "estimated_time": len(operation.target_ids) * 0.1,  # Rough estimate
        }
        db.commit()

    def _create_undo_operation(
        self, db: Session, original_operation: BulkOperation, user_id: int
    ) -> BulkOperation:
        """Create an undo operation for reversing changes"""
        # This is a simplified implementation - would need specific logic for each operation type
        undo_operation = BulkOperation(
            user_id=user_id,
            operation_type=original_operation.operation_type,
            operation_name=f"Undo: {original_operation.operation_name}",
            description=f"Undoing operation {original_operation.id}",
            target_ids=original_operation.target_ids,
            operation_params={"undo_data": original_operation.undo_data},
            total_items=len(original_operation.target_ids),
            is_undoable=False,  # Undo operations themselves are not undoable
        )

        db.add(undo_operation)
        db.commit()
        db.refresh(undo_operation)

        return undo_operation


# Initialize service instance
bulk_operations_service = BulkOperationsService()
