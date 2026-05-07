"""
Bulk Operations Models for MVidarr 0.9.7 - Issue #74
Database models for bulk operations, progress tracking, audit trail, and undo/redo functionality.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from src.database.connection import Base


class BulkOperationType(Enum):
    """Bulk operation type enumeration"""

    VIDEO_STATUS_UPDATE = "VIDEO_STATUS_UPDATE"
    VIDEO_METADATA_UPDATE = "VIDEO_METADATA_UPDATE"
    VIDEO_DELETE = "VIDEO_DELETE"
    VIDEO_DOWNLOAD = "VIDEO_DOWNLOAD"
    VIDEO_MERGE = "VIDEO_MERGE"
    VIDEO_TRANSCODE = "VIDEO_TRANSCODE"
    VIDEO_QUALITY_UPGRADE = "VIDEO_QUALITY_UPGRADE"
    VIDEO_ORGANIZE = "VIDEO_ORGANIZE"

    ARTIST_METADATA_UPDATE = "ARTIST_METADATA_UPDATE"
    ARTIST_DELETE = "ARTIST_DELETE"
    ARTIST_IMPORT = "ARTIST_IMPORT"
    ARTIST_ORGANIZE = "ARTIST_ORGANIZE"
    ARTIST_THUMBNAIL_SCAN = "ARTIST_THUMBNAIL_SCAN"

    DOWNLOAD_PRIORITY_UPDATE = "DOWNLOAD_PRIORITY_UPDATE"
    DOWNLOAD_QUEUE_MANAGEMENT = "DOWNLOAD_QUEUE_MANAGEMENT"

    CUSTOM = "CUSTOM"


class BulkOperationStatus(Enum):
    """Bulk operation status enumeration"""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"


class BulkOperation(Base):
    """Bulk operation tracking and management"""

    __tablename__ = "bulk_operations"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Operation details
    operation_type = Column(SQLEnum(BulkOperationType), nullable=False)
    operation_name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Target data
    target_ids = Column(JSON, nullable=False)  # List of IDs to process
    operation_params = Column(JSON, nullable=True)  # Operation-specific parameters

    # Status and progress
    status = Column(SQLEnum(BulkOperationStatus), default=BulkOperationStatus.PENDING)
    total_items = Column(Integer, nullable=False)
    processed_items = Column(Integer, default=0)
    successful_items = Column(Integer, default=0)
    failed_items = Column(Integer, default=0)
    progress_percentage = Column(Float, default=0.0)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    estimated_completion = Column(DateTime, nullable=True)

    # Results and errors
    results = Column(JSON, nullable=True)  # Detailed results
    error_log = Column(JSON, nullable=True)  # List of errors

    # Undo/Redo support
    is_undoable = Column(Boolean, default=True)
    undo_data = Column(JSON, nullable=True)  # Data needed for undo
    undone_at = Column(DateTime, nullable=True)
    undone_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Preview mode
    is_preview = Column(Boolean, default=False)
    preview_results = Column(JSON, nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id], backref="bulk_operations")
    undone_by_user = relationship("User", foreign_keys=[undone_by])
    progress_updates = relationship(
        "BulkOperationProgress",
        back_populates="operation",
        cascade="all, delete-orphan",
    )
    audit_entries = relationship(
        "BulkOperationAudit", back_populates="operation", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_bulk_operation_user_id", "user_id"),
        Index("idx_bulk_operation_type", "operation_type"),
        Index("idx_bulk_operation_status", "status"),
        Index("idx_bulk_operation_created", "created_at"),
        Index("idx_bulk_operation_undoable", "is_undoable"),
        Index("idx_bulk_operation_composite", "user_id", "status", "created_at"),
        {"extend_existing": True},
    )

    def update_progress(
        self, processed: int = None, successful: int = None, failed: int = None
    ):
        """Update operation progress"""
        if processed is not None:
            self.processed_items = processed
        if successful is not None:
            self.successful_items = successful
        if failed is not None:
            self.failed_items = failed

        if self.total_items > 0:
            self.progress_percentage = (self.processed_items / self.total_items) * 100

        # Update status based on progress
        if self.processed_items >= self.total_items:
            if self.failed_items == 0:
                self.status = BulkOperationStatus.COMPLETED
            elif self.successful_items > 0:
                self.status = BulkOperationStatus.PARTIALLY_COMPLETED
            else:
                self.status = BulkOperationStatus.FAILED

            self.completed_at = datetime.utcnow()

    def add_error(self, item_id: Any, error_message: str):
        """Add an error to the error log"""
        if self.error_log is None:
            self.error_log = []

        self.error_log.append(
            {
                "item_id": item_id,
                "error": error_message,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    def can_undo(self) -> bool:
        """Check if operation can be undone"""
        return (
            self.is_undoable
            and self.status
            in [BulkOperationStatus.COMPLETED, BulkOperationStatus.PARTIALLY_COMPLETED]
            and self.undone_at is None
            and self.undo_data is not None
        )

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """Convert operation to dictionary"""
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "operation_type": self.operation_type.value,
            "operation_name": self.operation_name,
            "description": self.description,
            "status": self.status.value,
            "total_items": self.total_items,
            "processed_items": self.processed_items,
            "successful_items": self.successful_items,
            "failed_items": self.failed_items,
            "progress_percentage": self.progress_percentage,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "estimated_completion": (
                self.estimated_completion.isoformat()
                if self.estimated_completion
                else None
            ),
            "is_undoable": self.is_undoable,
            "can_undo": self.can_undo(),
            "undone_at": self.undone_at.isoformat() if self.undone_at else None,
            "is_preview": self.is_preview,
        }

        if include_sensitive:
            data.update(
                {
                    "target_ids": self.target_ids,
                    "operation_params": self.operation_params,
                    "results": self.results,
                    "error_log": self.error_log,
                    "undo_data": self.undo_data,
                    "preview_results": self.preview_results,
                }
            )

        return data

    def __repr__(self):
        return f"<BulkOperation(id={self.id}, type='{self.operation_type.value}', status='{self.status.value}')>"


class BulkOperationProgress(Base):
    """Real-time progress tracking for bulk operations"""

    __tablename__ = "bulk_operation_progress"

    id = Column(Integer, primary_key=True)
    operation_id = Column(Integer, ForeignKey("bulk_operations.id"), nullable=False)

    # Progress details
    current_item_id = Column(String(100), nullable=True)  # Current item being processed
    current_item_name = Column(String(500), nullable=True)  # Human-readable name
    stage = Column(String(100), nullable=True)  # Current processing stage
    stage_progress = Column(Float, default=0.0)  # Progress within current stage

    # Performance metrics
    items_per_second = Column(Float, nullable=True)
    estimated_time_remaining = Column(Integer, nullable=True)  # Seconds

    # Status message
    status_message = Column(Text, nullable=True)

    # Timestamp
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    operation = relationship("BulkOperation", back_populates="progress_updates")

    # Indexes
    __table_args__ = (
        Index("idx_bulk_progress_operation", "operation_id"),
        Index("idx_bulk_progress_updated", "updated_at"),
        {"extend_existing": True},
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert progress to dictionary"""
        return {
            "id": self.id,
            "operation_id": self.operation_id,
            "current_item_id": self.current_item_id,
            "current_item_name": self.current_item_name,
            "stage": self.stage,
            "stage_progress": self.stage_progress,
            "items_per_second": self.items_per_second,
            "estimated_time_remaining": self.estimated_time_remaining,
            "status_message": self.status_message,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<BulkOperationProgress(operation_id={self.operation_id}, stage='{self.stage}')>"


class BulkOperationAudit(Base):
    """Audit trail for bulk operations and changes"""

    __tablename__ = "bulk_operation_audit"

    id = Column(Integer, primary_key=True)
    operation_id = Column(Integer, ForeignKey("bulk_operations.id"), nullable=False)

    # Item details
    item_type = Column(
        String(50), nullable=False
    )  # 'video', 'artist', 'download', etc.
    item_id = Column(Integer, nullable=False)

    # Change details
    action = Column(String(50), nullable=False)  # 'update', 'delete', 'create', etc.
    field_name = Column(String(100), nullable=True)  # Field that was changed
    old_value = Column(JSON, nullable=True)  # Previous value
    new_value = Column(JSON, nullable=True)  # New value

    # Context
    change_reason = Column(String(255), nullable=True)
    batch_sequence = Column(Integer, nullable=True)  # Order within batch

    # Metadata
    change_metadata = Column(JSON, nullable=True)  # Additional change context
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationships
    operation = relationship("BulkOperation", back_populates="audit_entries")

    # Indexes
    __table_args__ = (
        Index("idx_bulk_audit_operation", "operation_id"),
        Index("idx_bulk_audit_item", "item_type", "item_id"),
        Index("idx_bulk_audit_timestamp", "timestamp"),
        Index("idx_bulk_audit_action", "action"),
        {"extend_existing": True},
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert audit entry to dictionary"""
        return {
            "id": self.id,
            "operation_id": self.operation_id,
            "item_type": self.item_type,
            "item_id": self.item_id,
            "action": self.action,
            "field_name": self.field_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "change_reason": self.change_reason,
            "batch_sequence": self.batch_sequence,
            "change_metadata": self.change_metadata,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }

    def __repr__(self):
        return f"<BulkOperationAudit(operation_id={self.operation_id}, item={self.item_type}:{self.item_id})>"


class BulkOperationTemplate(Base):
    """Saved templates for bulk operations"""

    __tablename__ = "bulk_operation_templates"

    id = Column(Integer, primary_key=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=True
    )  # NULL for system templates

    # Template details
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    operation_type = Column(SQLEnum(BulkOperationType), nullable=False)

    # Template configuration
    template_params = Column(JSON, nullable=False)  # Default parameters
    target_criteria = Column(JSON, nullable=True)  # How to select target items

    # Sharing and usage
    is_public = Column(Boolean, default=False)
    is_system = Column(Boolean, default=False)
    usage_count = Column(Integer, default=0)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", backref="bulk_operation_templates")

    # Indexes
    __table_args__ = (
        Index("idx_bulk_template_user", "user_id"),
        Index("idx_bulk_template_type", "operation_type"),
        Index("idx_bulk_template_public", "is_public"),
        Index("idx_bulk_template_system", "is_system"),
        Index("idx_bulk_template_usage", "usage_count"),
        {"extend_existing": True},
    )

    def increment_usage(self):
        """Increment usage count and update last used timestamp"""
        self.usage_count += 1
        self.last_used_at = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert template to dictionary"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description,
            "operation_type": self.operation_type.value,
            "template_params": self.template_params,
            "target_criteria": self.target_criteria,
            "is_public": self.is_public,
            "is_system": self.is_system,
            "usage_count": self.usage_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_used_at": (
                self.last_used_at.isoformat() if self.last_used_at else None
            ),
        }

    def __repr__(self):
        return f"<BulkOperationTemplate(name='{self.name}', type='{self.operation_type.value}')>"
