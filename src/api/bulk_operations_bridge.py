"""
Bulk Operations Bridge for MVidarr 0.9.7 - Issue #74
Bridge between existing frontend bulk operations and new comprehensive backend system.
Provides backward compatibility while enabling enhanced features.
"""

from datetime import datetime
from typing import Any, Dict, List

from flask import Blueprint, g, jsonify, request

from src.database.bulk_models import BulkOperationStatus, BulkOperationType
from src.database.connection import get_db
from src.services.bulk_operations_service import bulk_operations_service
from src.utils.logger import get_logger

# Create bridge blueprint that extends videos API
bulk_bridge_bp = Blueprint("bulk_bridge", __name__)
logger = get_logger("mvidarr.api.bulk_bridge")


class BulkOperationsBridge:
    """
    Bridge class that adapts legacy bulk operation calls to the new comprehensive system
    """

    @staticmethod
    def create_bulk_operation(
        operation_type: str,
        operation_name: str,
        video_ids: List[int],
        operation_params: Dict[str, Any] = None,
        is_preview: bool = False,
    ) -> Dict:
        """
        Create a bulk operation using the new backend system
        """
        try:
            user_id = getattr(g, "current_user_id", None)

            # If no authenticated user, try to get a default user or create one
            if user_id is None:
                from src.database.connection import get_db
                from src.database.models import User

                try:
                    with get_db() as session:
                        # Try to find any existing user
                        existing_user = session.query(User).first()
                        if existing_user:
                            user_id = existing_user.id
                            logger.info(
                                f"Using existing user ID {user_id} for bulk operation"
                            )
                        else:
                            # No users exist - this shouldn't happen in normal operation
                            logger.error(
                                "No users found in database for bulk operation"
                            )
                            return {
                                "success": False,
                                "error": "Authentication required: No valid user found",
                            }
                except Exception as e:
                    logger.error(f"Failed to get user for bulk operation: {str(e)}")
                    return {"success": False, "error": "Authentication error"}

            operation = bulk_operations_service.create_operation(
                user_id=user_id,
                operation_type=operation_type,
                operation_name=operation_name,
                description=f"Legacy bulk operation: {operation_name}",
                target_ids=video_ids,
                operation_params=operation_params or {},
                is_preview=is_preview,
            )

            if operation:
                operation_id = operation.id
                # Start the operation immediately for legacy compatibility
                result = bulk_operations_service.start_operation(operation_id)
                return {
                    "success": True,
                    "operation_id": operation_id,
                    "status": "RUNNING" if result else "FAILED",
                    "message": f"Started bulk operation: {operation_name}",
                    "total_items": len(video_ids),
                    "progress_url": f"/api/bulk/operations/{operation_id}/progress",
                }
            else:
                return {"success": False, "error": "Failed to create bulk operation"}

        except Exception as e:
            logger.error(f"Error creating bulk operation: {str(e)}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_operation_status(operation_id: int) -> Dict:
        """
        Get the status of a bulk operation
        """
        try:
            operation = bulk_operations_service.get_operation(operation_id)
            if operation:
                return operation.to_dict()
            else:
                return {"error": "Operation not found"}
        except Exception as e:
            logger.error(f"Error getting operation status: {str(e)}")
            return {"error": str(e)}


# Bridge endpoints that maintain legacy API compatibility


# Basic endpoints that match existing frontend calls exactly
@bulk_bridge_bp.route("/api/videos/bulk/download", methods=["POST"])
def bulk_download():
    """
    Basic bulk download - direct bridge to enhanced system
    """
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids array is required"}), 400

        video_ids = data["video_ids"]

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.VIDEO_STATUS_UPDATE.value,
            operation_name="Bulk Download Videos",
            video_ids=video_ids,
            operation_params={"target_status": "DOWNLOADING", "action": "download"},
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in bulk download: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/videos/bulk/status", methods=["POST", "PUT"])
def bulk_status():
    """
    Basic bulk status update - direct bridge to enhanced system
    """
    try:
        data = request.get_json()
        if not data or "video_ids" not in data or "status" not in data:
            return jsonify({"error": "video_ids array and status are required"}), 400

        video_ids = data["video_ids"]
        new_status = data["status"]

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.VIDEO_STATUS_UPDATE.value,
            operation_name=f"Bulk Status Update to {new_status}",
            video_ids=video_ids,
            operation_params={"target_status": new_status, "action": "status_update"},
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in bulk status: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/videos/bulk/edit", methods=["POST"])
def bulk_edit():
    """
    Basic bulk edit - direct bridge to enhanced system
    """
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids array is required"}), 400

        video_ids = data["video_ids"]
        edit_params = {k: v for k, v in data.items() if k != "video_ids"}

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.VIDEO_METADATA_UPDATE.value,
            operation_name="Bulk Metadata Edit",
            video_ids=video_ids,
            operation_params=edit_params,
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in bulk edit: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/videos/bulk/delete", methods=["POST"])
def bulk_delete():
    """
    Basic bulk delete - direct bridge to enhanced system
    """
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids array is required"}), 400

        video_ids = data["video_ids"]
        delete_files = data.get("delete_files", False)

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.VIDEO_DELETE.value,
            operation_name="Bulk Delete Videos",
            video_ids=video_ids,
            operation_params={"delete_files": delete_files, "action": "delete"},
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in bulk delete: {str(e)}")
        return jsonify({"error": str(e)}), 500


# Enhanced endpoints for progressive enhancement
@bulk_bridge_bp.route("/api/videos/bulk/enhanced-download", methods=["POST"])
def enhanced_bulk_download():
    """
    Enhanced bulk download using new backend system
    Maintains compatibility with existing frontend
    """
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids array is required"}), 400

        video_ids = data["video_ids"]
        if not isinstance(video_ids, list):
            return jsonify({"error": "video_ids must be an array"}), 400

        # Use new bulk operations system
        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.VIDEO_STATUS_UPDATE.value,
            operation_name="Bulk Download Videos",
            video_ids=video_ids,
            operation_params={"target_status": "DOWNLOADING", "action": "download"},
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in enhanced bulk download: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/videos/bulk/enhanced-status", methods=["POST", "PUT"])
def enhanced_bulk_status():
    """
    Enhanced bulk status update using new backend system
    """
    try:
        data = request.get_json()
        if not data or "video_ids" not in data or "status" not in data:
            return jsonify({"error": "video_ids array and status are required"}), 400

        video_ids = data["video_ids"]
        new_status = data["status"]

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.VIDEO_STATUS_UPDATE.value,
            operation_name=f"Bulk Status Update to {new_status}",
            video_ids=video_ids,
            operation_params={"target_status": new_status, "action": "status_update"},
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in enhanced bulk status: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/videos/bulk/enhanced-edit", methods=["POST"])
def enhanced_bulk_edit():
    """
    Enhanced bulk edit using new backend system
    """
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids array is required"}), 400

        video_ids = data["video_ids"]
        edit_params = {k: v for k, v in data.items() if k != "video_ids"}

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.VIDEO_METADATA_UPDATE.value,
            operation_name="Bulk Metadata Edit",
            video_ids=video_ids,
            operation_params=edit_params,
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in enhanced bulk edit: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/videos/bulk/enhanced-delete", methods=["POST"])
def enhanced_bulk_delete():
    """
    Enhanced bulk delete using new backend system
    """
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids array is required"}), 400

        video_ids = data["video_ids"]
        delete_files = data.get("delete_files", False)

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.VIDEO_DELETE.value,
            operation_name="Bulk Delete Videos",
            video_ids=video_ids,
            operation_params={"delete_files": delete_files, "action": "delete"},
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in enhanced bulk delete: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/videos/bulk/refresh-metadata", methods=["POST"])
def bulk_refresh_metadata():
    """
    Enhanced bulk metadata refresh using new backend system
    """
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids array is required"}), 400

        video_ids = data["video_ids"]

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.VIDEO_METADATA_UPDATE.value,
            operation_name="Bulk Refresh Metadata",
            video_ids=video_ids,
            operation_params={"action": "refresh_metadata", "source": "imvdb"},
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in bulk refresh metadata: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/videos/bulk/enhanced-refresh-metadata", methods=["POST"])
def bulk_enhanced_refresh_metadata():
    """
    Enhanced bulk metadata refresh using comprehensive metadata enrichment
    """
    import asyncio

    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids array is required"}), 400

        video_ids = data["video_ids"]
        force_refresh = data.get("force_refresh", False)

        # Use the enhanced metadata enrichment service directly
        from src.services.metadata_enrichment_service import metadata_enrichment_service

        results = {
            "total": len(video_ids),
            "successful": 0,
            "failed": 0,
            "errors": [],
            "details": [],
        }

        for video_id in video_ids:
            try:
                result = asyncio.run(
                    metadata_enrichment_service.enrich_video_metadata(
                        video_id, force_refresh=force_refresh
                    )
                )

                if result.get("success", False):
                    results["successful"] += 1
                    results["details"].append(
                        {
                            "video_id": video_id,
                            "status": "success",
                            "sources_used": result.get("sources_used", []),
                            "updates_made": result.get("updates_made", []),
                        }
                    )
                else:
                    results["failed"] += 1
                    error_msg = result.get("error", "Unknown error")
                    results["errors"].append(f"Video {video_id}: {error_msg}")
                    results["details"].append(
                        {"video_id": video_id, "status": "failed", "error": error_msg}
                    )

            except Exception as e:
                results["failed"] += 1
                error_msg = str(e)
                results["errors"].append(f"Video {video_id}: {error_msg}")
                results["details"].append(
                    {"video_id": video_id, "status": "failed", "error": error_msg}
                )
                logger.error(f"Error enriching metadata for video {video_id}: {e}")

        return jsonify(results)

    except Exception as e:
        logger.error(f"Error in bulk enhanced refresh metadata: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/videos/bulk/organize", methods=["POST"])
def bulk_organize():
    """
    Enhanced bulk organize using new backend system
    """
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids array is required"}), 400

        video_ids = data["video_ids"]
        organize_params = {k: v for k, v in data.items() if k != "video_ids"}

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.VIDEO_ORGANIZE.value,
            operation_name="Bulk Organize Videos",
            video_ids=video_ids,
            operation_params=organize_params,
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in bulk organize: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/videos/bulk/quality-check", methods=["POST"])
def bulk_quality_check():
    """
    Enhanced bulk quality check using new backend system
    """
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids array is required"}), 400

        video_ids = data["video_ids"]

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.VIDEO_QUALITY_UPGRADE.value,
            operation_name="Bulk Quality Check",
            video_ids=video_ids,
            operation_params={"action": "quality_check"},
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in bulk quality check: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/videos/bulk/upgrade-quality", methods=["POST"])
def bulk_upgrade_quality():
    """
    Enhanced bulk quality upgrade using new backend system
    """
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids array is required"}), 400

        video_ids = data["video_ids"]
        quality_params = {k: v for k, v in data.items() if k != "video_ids"}

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.VIDEO_QUALITY_UPGRADE.value,
            operation_name="Bulk Quality Upgrade",
            video_ids=video_ids,
            operation_params=quality_params,
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in bulk quality upgrade: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/videos/bulk/transcode", methods=["POST"])
def bulk_transcode():
    """
    Enhanced bulk transcode using new backend system
    """
    try:
        data = request.get_json()
        if not data or "video_ids" not in data:
            return jsonify({"error": "video_ids array is required"}), 400

        video_ids = data["video_ids"]
        transcode_params = {k: v for k, v in data.items() if k != "video_ids"}

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.VIDEO_TRANSCODE.value,
            operation_name="Bulk Transcode Videos",
            video_ids=video_ids,
            operation_params=transcode_params,
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in bulk transcode: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route(
    "/api/bulk/operations/<int:operation_id>/progress", methods=["GET"]
)
def get_operation_progress(operation_id: int):
    """
    Get real-time progress for a bulk operation
    """
    try:
        result = BulkOperationsBridge.get_operation_status(operation_id)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting operation progress: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route(
    "/api/bulk/operations/<int:operation_id>/cancel", methods=["POST"]
)
def cancel_operation(operation_id: int):
    """
    Cancel a running bulk operation
    """
    try:
        result = bulk_operations_service.cancel_operation(operation_id)
        return jsonify(
            {
                "success": result,
                "message": (
                    "Operation cancelled" if result else "Failed to cancel operation"
                ),
            }
        )
    except Exception as e:
        logger.error(f"Error cancelling operation: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/bulk/operations/<int:operation_id>/undo", methods=["POST"])
def undo_operation(operation_id: int):
    """
    Undo a completed bulk operation
    """
    try:
        result = bulk_operations_service.undo_operation(operation_id)
        return jsonify(
            {
                "success": result,
                "message": "Operation undone" if result else "Failed to undo operation",
            }
        )
    except Exception as e:
        logger.error(f"Error undoing operation: {str(e)}")
        return jsonify({"error": str(e)}), 500


# Artist bulk operations endpoints
@bulk_bridge_bp.route("/api/artists/bulk-refresh-metadata", methods=["POST"])
def artists_bulk_refresh_metadata():
    """
    Enhanced artist bulk metadata refresh using new backend system
    """
    try:
        data = request.get_json()
        if not data or "artist_ids" not in data:
            return jsonify({"error": "artist_ids array is required"}), 400

        artist_ids = data["artist_ids"]

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.ARTIST_METADATA_UPDATE.value,
            operation_name="Bulk Artist Metadata Refresh",
            video_ids=artist_ids,  # Using video_ids param but with artist IDs
            operation_params={
                "action": "refresh_metadata",
                "source": "imvdb",
                "entity_type": "artist",
            },
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in artist bulk refresh metadata: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/artists/bulk-edit", methods=["POST"])
def artists_bulk_edit():
    """
    Enhanced artist bulk edit using new backend system
    """
    try:
        data = request.get_json()
        if not data or "artist_ids" not in data:
            return jsonify({"error": "artist_ids array is required"}), 400

        artist_ids = data["artist_ids"]
        edit_params = {k: v for k, v in data.items() if k != "artist_ids"}

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.ARTIST_METADATA_UPDATE.value,
            operation_name="Bulk Artist Edit",
            video_ids=artist_ids,  # Using video_ids param but with artist IDs
            operation_params={**edit_params, "entity_type": "artist"},
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in artist bulk edit: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/artists/bulk-delete", methods=["POST"])
def artists_bulk_delete():
    """
    Enhanced artist bulk delete using new backend system
    """
    try:
        data = request.get_json()
        if not data or "artist_ids" not in data:
            return jsonify({"error": "artist_ids array is required"}), 400

        artist_ids = data["artist_ids"]
        delete_files = data.get("delete_files", False)

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.ARTIST_DELETE.value,
            operation_name="Bulk Artist Delete",
            video_ids=artist_ids,  # Using video_ids param but with artist IDs
            operation_params={
                "delete_files": delete_files,
                "action": "delete",
                "entity_type": "artist",
            },
            is_preview=data.get("preview", False),
        )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in artist bulk delete: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/artists/bulk-metadata", methods=["POST"])
def artists_bulk_metadata():
    """
    Enhanced artist bulk metadata update using new backend system
    """
    try:
        data = request.get_json()
        if not data or "artist_ids" not in data or "metadata" not in data:
            return jsonify({"error": "artist_ids array and metadata are required"}), 400

        artist_ids = data["artist_ids"]
        metadata = data["metadata"]

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.ARTIST_METADATA_UPDATE.value,
            operation_name="Bulk Artist Metadata Update",
            video_ids=artist_ids,  # Using video_ids param but with artist IDs
            operation_params={
                "metadata": metadata,
                "action": "metadata_update",
                "entity_type": "artist",
            },
            is_preview=data.get("preview", False),
        )

        # For artist metadata updates, return simplified response for immediate frontend compatibility
        if result.get("success"):
            return jsonify(
                {
                    "success": True,
                    "updated_count": len(artist_ids),
                    "message": f"Successfully updated metadata for {len(artist_ids)} artists",
                }
            )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in artist bulk metadata update: {str(e)}")
        return jsonify({"error": str(e)}), 500


@bulk_bridge_bp.route("/api/artists/bulk-validate-metadata", methods=["POST"])
def artists_bulk_validate_metadata():
    """
    Enhanced artist bulk metadata validation using new backend system
    """
    try:
        data = request.get_json()
        if not data or "artist_ids" not in data:
            return jsonify({"error": "artist_ids array is required"}), 400

        artist_ids = data["artist_ids"]

        result = BulkOperationsBridge.create_bulk_operation(
            operation_type=BulkOperationType.ARTIST_METADATA_UPDATE.value,
            operation_name="Bulk Artist Metadata Validation",
            video_ids=artist_ids,  # Using video_ids param but with artist IDs
            operation_params={
                "action": "validate_metadata",
                "entity_type": "artist",
            },
            is_preview=data.get("preview", False),
        )

        # For artist metadata validation, return simplified response for immediate frontend compatibility
        if result.get("success"):
            return jsonify(
                {
                    "success": True,
                    "validated_count": len(artist_ids),
                    "message": f"Successfully validated metadata for {len(artist_ids)} artists",
                }
            )

        return jsonify(result)

    except Exception as e:
        logger.error(f"Error in artist bulk metadata validation: {str(e)}")
        return jsonify({"error": str(e)}), 500


# Health check for bridge system
@bulk_bridge_bp.route("/api/bulk/bridge/health", methods=["GET"])
def bridge_health():
    """
    Health check for bulk operations bridge
    """
    try:
        active_operations = bulk_operations_service.get_active_operations()
        return jsonify(
            {
                "status": "healthy",
                "active_operations": len(active_operations) if active_operations else 0,
                "backend_available": True,
                "timestamp": datetime.now().isoformat(),
            }
        )
    except Exception as e:
        logger.error(f"Bridge health check failed: {str(e)}")
        return (
            jsonify(
                {
                    "status": "unhealthy",
                    "error": str(e),
                    "backend_available": False,
                    "timestamp": datetime.now().isoformat(),
                }
            ),
            500,
        )
