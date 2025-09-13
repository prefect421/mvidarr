"""
Metadata Enrichment API endpoints for Issue #75
Multi-source artist discovery and metadata aggregation endpoints
"""

import asyncio

from flask import Blueprint, jsonify, request
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.database.models import Artist
from src.middleware.simple_auth_middleware import auth_required
from src.services.duplicate_detection_service import duplicate_detection_service
from src.services.metadata_enrichment_service import metadata_enrichment_service
from src.services.metadata_validation_service import metadata_validation_service
from src.utils.logger import get_logger

metadata_enrichment_bp = Blueprint(
    "metadata_enrichment", __name__, url_prefix="/metadata-enrichment"
)
logger = get_logger("mvidarr.api.metadata_enrichment")


@metadata_enrichment_bp.route("/enrich/<int:artist_id>", methods=["POST"])
@auth_required
def enrich_artist_metadata(artist_id: int):
    """Enrich metadata for a specific artist using Celery background task"""
    try:
        force_refresh = (
            request.json.get("force_refresh", False) if request.is_json else False
        )
        enrich_videos = (
            request.json.get("enrich_videos", True) if request.is_json else True
        )

        # Import Celery task
        from src.jobs.metadata_tasks import enrich_artist_metadata_task

        # Queue the Celery task
        task = enrich_artist_metadata_task.delay(
            artist_id=artist_id,
            force_refresh=force_refresh,
            enrich_videos=enrich_videos,
        )

        logger.info(
            f"Queued Celery metadata enrichment task {task.id} for artist {artist_id}"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "job_id": task.id,
                    "artist_id": artist_id,
                    "status": "queued",
                    "message": f"Metadata enrichment job started for artist {artist_id}",
                    "task_state": task.state,
                    "note": "Background processing initiated",
                }
            ),
            202,
        )  # 202 Accepted - processing started

    except Exception as e:
        logger.error(f"Failed to queue Celery metadata enrichment task: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/enrich/video/<int:video_id>", methods=["POST"])
@auth_required
def enrich_video_metadata(video_id: int):
    """Enrich metadata for a specific video using Celery background task"""
    try:
        force_refresh = (
            request.json.get("force_refresh", False) if request.is_json else False
        )

        # Import Celery task
        from src.jobs.metadata_tasks import enrich_video_metadata_task

        # Queue the Celery task
        task = enrich_video_metadata_task.delay(
            video_id=video_id, force_refresh=force_refresh
        )

        logger.info(
            f"Queued Celery video metadata enrichment task {task.id} for video {video_id}"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "job_id": task.id,
                    "video_id": video_id,
                    "status": "queued",
                    "message": f"Video metadata enrichment job started for video {video_id}",
                    "task_state": task.state,
                }
            ),
            202,
        )  # 202 Accepted - processing started

    except Exception as e:
        logger.error(f"Failed to queue Celery video metadata enrichment task: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/enrich/batch", methods=["POST"])
@auth_required
def enrich_multiple_artists():
    """Enrich metadata for multiple artists using Celery batch task"""
    try:
        if not request.is_json:
            return jsonify({"error": "JSON payload required"}), 400

        data = request.get_json()
        artist_ids = data.get("artist_ids", [])
        force_refresh = data.get("force_refresh", False)
        enrich_videos = data.get("enrich_videos", True)

        if not artist_ids:
            return jsonify({"error": "artist_ids list is required"}), 400

        if not isinstance(artist_ids, list):
            return jsonify({"error": "artist_ids must be a list"}), 400

        # Validate all IDs are integers
        try:
            artist_ids = [int(aid) for aid in artist_ids]
        except (ValueError, TypeError):
            return jsonify({"error": "All artist_ids must be valid integers"}), 400

        # Import Celery task
        from src.jobs.metadata_tasks import batch_enrich_artists_task

        # Queue the Celery batch task
        task = batch_enrich_artists_task.delay(
            artist_ids=artist_ids,
            force_refresh=force_refresh,
            enrich_videos=enrich_videos,
        )

        logger.info(
            f"Queued Celery batch metadata enrichment task {task.id} for {len(artist_ids)} artists"
        )

        return (
            jsonify(
                {
                    "success": True,
                    "job_id": task.id,
                    "task_ids": [task.id],  # For backward compatibility
                    "total_artists": len(artist_ids),
                    "status": "queued",
                    "message": f"Queued batch metadata enrichment for {len(artist_ids)} artists",
                    "task_state": task.state,
                }
            ),
            202,
        )  # 202 Accepted - processing started

    except Exception as e:
        logger.error(f"Failed to queue Celery batch metadata enrichment task: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/job/<task_id>/status", methods=["GET"])
@auth_required
def get_job_status(task_id: str):
    """Get the status of a Celery metadata enrichment job"""
    try:
        from src.jobs.celery_app import celery_app

        # Get task result object
        result = celery_app.AsyncResult(task_id)

        # Build response based on task state
        if result.state == "PENDING":
            response = {
                "job_id": task_id,
                "status": "pending",
                "progress": 0,
                "message": "Task is waiting to be processed...",
                "state": result.state,
            }
        elif result.state == "PROGRESS":
            response = {
                "job_id": task_id,
                "status": "progress",
                "progress": result.info.get("progress", 0),
                "message": result.info.get("message", "Processing..."),
                "state": result.state,
                "timestamp": result.info.get("timestamp"),
            }
        elif result.state == "SUCCESS":
            response = {
                "job_id": task_id,
                "status": "completed",
                "progress": 100,
                "message": "Task completed successfully",
                "state": result.state,
                "result": result.result,
            }
        elif result.state == "FAILURE":
            response = {
                "job_id": task_id,
                "status": "failed",
                "progress": 0,
                "message": f"Task failed: {str(result.info)}",
                "state": result.state,
                "error": str(result.info),
                "traceback": result.traceback,
            }
        else:
            response = {
                "job_id": task_id,
                "status": result.state.lower(),
                "progress": 0,
                "message": f"Task state: {result.state}",
                "state": result.state,
            }

        return jsonify(response), 200

    except Exception as e:
        logger.error(f"Failed to get job status for {task_id}: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/job/<task_id>/cancel", methods=["POST"])
@auth_required
def cancel_job(task_id: str):
    """Cancel a running Celery metadata enrichment job"""
    try:
        from src.jobs.celery_app import job_manager

        success = job_manager.cancel_job(task_id)

        if success:
            return (
                jsonify(
                    {
                        "success": True,
                        "job_id": task_id,
                        "message": f"Job {task_id} has been cancelled",
                    }
                ),
                200,
            )
        else:
            return (
                jsonify(
                    {
                        "success": False,
                        "job_id": task_id,
                        "message": f"Failed to cancel job {task_id}",
                    }
                ),
                400,
            )

    except Exception as e:
        logger.error(f"Failed to cancel job {task_id}: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/stats", methods=["GET"])
@auth_required
def get_enrichment_stats():
    """Get metadata enrichment statistics"""
    try:
        stats = metadata_enrichment_service.get_enrichment_stats()
        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Failed to get enrichment stats: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/candidates", methods=["GET"])
@auth_required
def get_enrichment_candidates():
    """Get artists that are candidates for metadata enrichment"""
    try:
        # Parse query parameters
        limit = request.args.get("limit", 50, type=int)
        offset = request.args.get("offset", 0, type=int)
        missing_external_ids = (
            request.args.get("missing_external_ids", "false").lower() == "true"
        )
        outdated_only = request.args.get("outdated_only", "false").lower() == "true"

        with get_db() as session:
            query = session.query(Artist)

            # Filter for artists missing external IDs OR lacking enriched metadata
            if missing_external_ids:
                # Include artists missing external IDs OR those with IDs but no enriched metadata
                query = query.filter(
                    (Artist.spotify_id.is_(None))
                    | (Artist.spotify_id == "")
                    | (Artist.lastfm_name.is_(None))
                    | (Artist.lastfm_name == "")
                    | (Artist.imvdb_id.is_(None))
                    | (Artist.imvdb_id == "")
                    | (Artist.imvdb_metadata.is_(None))
                    | (Artist.imvdb_metadata == {})
                    | (~Artist.imvdb_metadata.contains("enrichment_date"))
                )

            # Import datetime at function level since it's used later regardless of conditions
            from datetime import datetime, timedelta

            # Filter for outdated metadata (older than cache duration)
            if outdated_only:
                # Check for artists with outdated metadata
                cache_duration = timedelta(hours=24)  # Match service configuration
                cutoff_date = datetime.now() - cache_duration

                # Artists with no enrichment metadata or old enrichment data
                query = query.filter(
                    (Artist.imvdb_metadata.is_(None))
                    | (Artist.imvdb_metadata == {})
                    | (Artist.imvdb_metadata.op("->>")("enrichment_date").is_(None))
                )

            # Order by updated_at to prioritize older records
            query = query.order_by(Artist.updated_at.asc())

            # Apply pagination
            total = query.count()
            artists = query.offset(offset).limit(limit).all()

            candidates = []
            for artist in artists:
                # Determine what's missing (consistent with statistics logic)
                missing_ids = []
                if not artist.spotify_id or (
                    isinstance(artist.spotify_id, str) and not artist.spotify_id.strip()
                ):
                    missing_ids.append("spotify")
                if not artist.lastfm_name or (
                    isinstance(artist.lastfm_name, str)
                    and not artist.lastfm_name.strip()
                ):
                    missing_ids.append("lastfm")
                if not artist.imvdb_id or (
                    isinstance(artist.imvdb_id, str) and not artist.imvdb_id.strip()
                ):
                    missing_ids.append("imvdb")

                # Check metadata freshness
                metadata_age = None
                if isinstance(
                    artist.imvdb_metadata, dict
                ) and artist.imvdb_metadata.get("enrichment_date"):
                    try:
                        enrichment_date = datetime.fromisoformat(
                            artist.imvdb_metadata["enrichment_date"]
                        )
                        metadata_age = (datetime.now() - enrichment_date).days
                    except (ValueError, TypeError):
                        metadata_age = None

                candidates.append(
                    {
                        "id": artist.id,
                        "name": artist.name,
                        "missing_external_ids": missing_ids,
                        "metadata_age_days": metadata_age,
                        "has_enriched_metadata": isinstance(artist.imvdb_metadata, dict)
                        and "enrichment_date" in artist.imvdb_metadata,
                        "last_updated": (
                            artist.updated_at.isoformat() if artist.updated_at else None
                        ),
                    }
                )

            return (
                jsonify(
                    {
                        "candidates": candidates,
                        "pagination": {
                            "total": total,
                            "limit": limit,
                            "offset": offset,
                            "has_more": offset + limit < total,
                        },
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to get enrichment candidates: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/auto-enrich", methods=["POST"])
@auth_required
def auto_enrich_candidates():
    """Automatically enrich candidates based on criteria"""
    try:
        if not request.is_json:
            return jsonify({"error": "JSON payload required"}), 400

        data = request.get_json()
        limit = data.get("limit", 10)  # Process up to 10 artists at once
        missing_external_ids = data.get("missing_external_ids", True)
        outdated_only = data.get("outdated_only", False)
        force_refresh = data.get("force_refresh", False)

        # Import datetime at function level for consistency
        from datetime import datetime, timedelta

        with get_db() as session:
            query = session.query(Artist)

            # Apply same filters as candidates endpoint
            if missing_external_ids:
                query = query.filter(
                    (Artist.spotify_id.is_(None))
                    | (Artist.spotify_id == "")
                    | (Artist.lastfm_name.is_(None))
                    | (Artist.lastfm_name == "")
                    | (Artist.imvdb_id.is_(None))
                    | (Artist.imvdb_id == "")
                    | (Artist.imvdb_metadata.is_(None))
                    | (Artist.imvdb_metadata == {})
                    | (~Artist.imvdb_metadata.contains("enrichment_date"))
                )

            if outdated_only:
                cache_duration = timedelta(hours=24)
                cutoff_date = datetime.now() - cache_duration

                query = query.filter(
                    (Artist.imvdb_metadata.is_(None))
                    | (Artist.imvdb_metadata == {})
                    | (Artist.imvdb_metadata.op("->>")("enrichment_date").is_(None))
                )

            # Get candidates ordered by priority
            candidates = query.order_by(Artist.updated_at.asc()).limit(limit).all()

            if not candidates:
                return (
                    jsonify(
                        {
                            "message": "No candidates found for enrichment",
                            "processed": 0,
                            "results": [],
                        }
                    ),
                    200,
                )

            # Extract artist IDs
            artist_ids = [artist.id for artist in candidates]

        # Run batch enrichment with Flask app context
        from flask import current_app

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(
                metadata_enrichment_service.enrich_multiple_artists(
                    artist_ids, force_refresh, app_context=current_app
                )
            )
        finally:
            loop.close()

        # Process results
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        return (
            jsonify(
                {
                    "message": f"Auto-enrichment completed for {len(results)} artists",
                    "processed": len(results),
                    "successful": len(successful),
                    "failed": len(failed),
                    "results": [
                        {
                            "artist_id": r.artist_id,
                            "success": r.success,
                            "sources_used": r.sources_used,
                            "confidence_score": r.confidence_score,
                            "errors": r.errors if not r.success else None,
                        }
                        for r in results
                    ],
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to auto-enrich candidates: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/artist/<int:artist_id>/metadata", methods=["GET"])
def get_artist_enriched_metadata(artist_id: int):
    """Get enriched metadata for a specific artist"""
    try:
        with get_db() as session:
            artist = session.query(Artist).filter(Artist.id == artist_id).first()

            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            # Extract enriched metadata from imvdb_metadata field
            enriched_metadata = {}
            if isinstance(artist.imvdb_metadata, dict):
                enriched_metadata = artist.imvdb_metadata

            return (
                jsonify(
                    {
                        "artist_id": artist.id,
                        "artist_name": artist.name,
                        "external_ids": {
                            "spotify": artist.spotify_id,
                            "lastfm": artist.lastfm_name,
                            "imvdb": artist.imvdb_id,
                            "musicbrainz": enriched_metadata.get("musicbrainz_id"),
                        },
                        "enriched_metadata": enriched_metadata,
                        "has_enriched_data": "enrichment_date" in enriched_metadata,
                        "last_updated": (
                            artist.updated_at.isoformat() if artist.updated_at else None
                        ),
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to get enriched metadata for artist {artist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/validate/<int:artist_id>", methods=["GET"])
def validate_artist_metadata(artist_id: int):
    """Validate metadata quality for a specific artist"""
    try:
        validation_result = metadata_validation_service.validate_artist_metadata(
            artist_id
        )

        return (
            jsonify(
                {
                    "artist_id": artist_id,
                    "is_valid": validation_result.is_valid,
                    "confidence_score": validation_result.confidence_score,
                    "data_quality_score": validation_result.data_quality_score,
                    "needs_enrichment": validation_result.needs_enrichment,
                    "issues": validation_result.issues,
                    "recommendations": validation_result.recommendations,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to validate metadata for artist {artist_id}: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/validation/report", methods=["GET"])
@auth_required
def get_validation_report():
    """Get a comprehensive validation report"""
    try:
        limit = request.args.get("limit", 100, type=int)
        report = metadata_validation_service.get_validation_report(limit)

        return jsonify(report), 200

    except Exception as e:
        logger.error(f"Failed to generate validation report: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/automation/run", methods=["POST"])
def run_automated_enrichment():
    """Run automated metadata enrichment"""
    try:
        if not request.is_json:
            data = {}
        else:
            data = request.get_json()

        limit = data.get("limit", 10)

        # Run automated enrichment
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            stats = loop.run_until_complete(
                metadata_validation_service.auto_enrich_candidates(limit)
            )
        finally:
            loop.close()

        return (
            jsonify(
                {
                    "success": True,
                    "stats": {
                        "run_date": stats.run_date.isoformat(),
                        "candidates_found": stats.candidates_found,
                        "enriched_count": stats.enriched_count,
                        "validation_failures": stats.validation_failures,
                        "avg_confidence_improvement": stats.avg_confidence_improvement,
                        "total_processing_time": stats.total_processing_time,
                    },
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to run automated enrichment: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/automation/schedule", methods=["POST"])
def schedule_automated_enrichment():
    """Schedule automated metadata enrichment"""
    try:
        success = metadata_validation_service.schedule_auto_enrichment()

        return (
            jsonify(
                {
                    "success": success,
                    "message": (
                        "Automated enrichment scheduled and executed"
                        if success
                        else "No artists were enriched"
                    ),
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to schedule automated enrichment: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/duplicates/candidates", methods=["GET"])
@auth_required
def get_duplicate_candidates():
    """Get potential duplicate artist candidates"""
    try:
        limit = request.args.get("limit", 50, type=int)
        min_confidence = request.args.get("min_confidence", 0.5, type=float)

        candidates = duplicate_detection_service.find_duplicate_candidates(limit)

        # Filter by minimum confidence
        filtered_candidates = [
            c for c in candidates if c.match_confidence >= min_confidence
        ]

        results = []
        for candidate in filtered_candidates:
            results.append(
                {
                    "artist1_id": candidate.artist1_id,
                    "artist2_id": candidate.artist2_id,
                    "artist1_name": candidate.artist1_name,
                    "artist2_name": candidate.artist2_name,
                    "similarity_score": candidate.similarity_score,
                    "match_confidence": candidate.match_confidence,
                    "match_reasons": candidate.match_reasons,
                    "external_id_matches": candidate.external_id_matches,
                    "metadata_overlap": candidate.metadata_overlap,
                    "recommended_action": candidate.recommended_action,
                }
            )

        return (
            jsonify(
                {
                    "candidates": results,
                    "total_found": len(filtered_candidates),
                    "min_confidence": min_confidence,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to get duplicate candidates: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/duplicates/stats", methods=["GET"])
def get_duplicate_stats():
    """Get duplicate detection statistics"""
    try:
        stats = duplicate_detection_service.get_duplicate_stats()
        return jsonify(stats), 200

    except Exception as e:
        logger.error(f"Failed to get duplicate stats: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/duplicates/merge", methods=["POST"])
@auth_required
def merge_duplicate_artists():
    """Merge duplicate artists"""
    try:
        if not request.is_json:
            return jsonify({"error": "JSON payload required"}), 400

        data = request.get_json()
        primary_artist_id = data.get("primary_artist_id")
        duplicate_artist_id = data.get("duplicate_artist_id")
        auto_merge = data.get("auto_merge", False)

        if not primary_artist_id or not duplicate_artist_id:
            return (
                jsonify(
                    {"error": "primary_artist_id and duplicate_artist_id are required"}
                ),
                400,
            )

        result = duplicate_detection_service.merge_duplicate_artists(
            primary_artist_id, duplicate_artist_id, auto_merge
        )

        if result.success:
            return (
                jsonify(
                    {
                        "success": True,
                        "primary_artist_id": result.primary_artist_id,
                        "merged_artist_id": result.merged_artist_id,
                        "videos_moved": result.videos_moved,
                        "downloads_moved": result.downloads_moved,
                        "metadata_merged": result.metadata_merged,
                    }
                ),
                200,
            )
        else:
            return jsonify({"success": False, "errors": result.errors}), 400

    except Exception as e:
        logger.error(f"Failed to merge duplicate artists: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/duplicates/auto-merge", methods=["POST"])
@auth_required
def auto_merge_duplicates():
    """Automatically merge high-confidence duplicate pairs"""
    try:
        if not request.is_json:
            data = {}
        else:
            data = request.get_json()

        limit = data.get("limit", 10)

        results = duplicate_detection_service.auto_merge_high_confidence_duplicates(
            limit
        )

        successful_merges = [r for r in results if r.success]
        failed_merges = [r for r in results if not r.success]

        return (
            jsonify(
                {
                    "total_processed": len(results),
                    "successful_merges": len(successful_merges),
                    "failed_merges": len(failed_merges),
                    "results": [
                        {
                            "primary_artist_id": r.primary_artist_id,
                            "merged_artist_id": r.merged_artist_id,
                            "success": r.success,
                            "videos_moved": r.videos_moved if r.success else None,
                            "downloads_moved": r.downloads_moved if r.success else None,
                            "errors": r.errors if not r.success else None,
                        }
                        for r in results
                    ],
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Failed to auto-merge duplicates: {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/blank-metadata-report/<int:artist_id>", methods=["GET"])
@auth_required
def get_blank_metadata_report(artist_id: int):
    """Get detailed report of blank/missing metadata fields for specific artist"""
    try:
        validation_service = metadata_validation_service
        report = validation_service.get_blank_metadata_report(artist_id)

        if "error" in report:
            return jsonify(report), (
                404 if "not found" in report["error"].lower() else 500
            )

        return jsonify(report), 200

    except Exception as e:
        logger.error(
            f"Failed to generate blank metadata report for artist {artist_id}: {e}"
        )
        return jsonify({"error": str(e)}), 500


# Search endpoints for metadata enrichment sources
@metadata_enrichment_bp.route("/search/lastfm", methods=["GET"])
@auth_required
def search_lastfm():
    """Search Last.fm for artist information"""
    try:
        artist_name = request.args.get("artist")
        if not artist_name:
            return jsonify({"error": "artist parameter is required"}), 400

        # Import the lastfm service
        from src.services.lastfm_service import lastfm_service

        # Check if Last.fm is properly configured
        if not lastfm_service.api_key:
            return (
                jsonify(
                    {
                        "results": [],
                        "message": "Last.fm API requires credentials. Please configure API key and secret in Settings.",
                        "authentication_required": True,
                    }
                ),
                200,
            )

        results = lastfm_service.search_artist(artist_name)
        if not results:
            return (
                jsonify(
                    {
                        "results": [],
                        "message": "No Last.fm results found or API credentials invalid.",
                        "authentication_required": not bool(lastfm_service.api_key),
                    }
                ),
                200,
            )

        return jsonify({"results": results}), 200

    except Exception as e:
        logger.error(f"Failed to search Last.fm for artist '{artist_name}': {e}")
        # Check if it's an authentication error
        if "API key not configured" in str(e):
            return (
                jsonify(
                    {
                        "results": [],
                        "message": "Last.fm API requires credentials. Please configure API key and secret in Settings.",
                        "authentication_required": True,
                    }
                ),
                200,
            )
        return jsonify({"error": str(e)}), 500


# Discogs search endpoint removed - service discontinued


@metadata_enrichment_bp.route("/search/allmusic", methods=["GET"])
@auth_required
def search_allmusic():
    """Search AllMusic for artist information"""
    try:
        artist_name = request.args.get("artist")
        if not artist_name:
            return jsonify({"error": "artist parameter is required"}), 400

        # Use AllMusic search via web scraping (no official API)
        from urllib.parse import quote

        import requests

        search_url = f"https://www.allmusic.com/search/artists/{quote(artist_name)}"
        headers = {
            "User-Agent": "MVidarr/0.9.8 (https://github.com/prefect421/mvidarr)"
        }

        try:
            response = requests.get(search_url, headers=headers, timeout=10)
            if response.status_code == 200:
                # Basic implementation - extract artist names from search results
                # This is a simplified approach since AllMusic doesn't have a public API
                results = []

                # Try to extract some basic info from the HTML (simplified)
                if artist_name.lower() in response.text.lower():
                    results.append(
                        {
                            "name": artist_name,
                            "id": artist_name.lower().replace(" ", "-"),
                            "url": f"https://www.allmusic.com/artist/{artist_name.lower().replace(' ', '-')}",
                            "source": "allmusic",
                        }
                    )

                return jsonify({"results": results}), 200
            else:
                logger.warning(
                    f"AllMusic search returned status {response.status_code}"
                )
                return jsonify({"results": []}), 200

        except requests.RequestException as e:
            logger.error(f"AllMusic request failed: {e}")
            return jsonify({"results": []}), 200

    except Exception as e:
        logger.error(f"Failed to search AllMusic for artist '{artist_name}': {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/search/wikipedia", methods=["GET"])
@auth_required
def search_wikipedia():
    """Search Wikipedia for artist information"""
    try:
        artist_name = request.args.get("artist")
        if not artist_name:
            return jsonify({"error": "artist parameter is required"}), 400

        # Import wikipedia service or implement basic search
        import requests

        # Use Wikipedia's OpenSearch API (more reliable)
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "opensearch",
            "search": artist_name,
            "limit": 5,
            "namespace": 0,
            "format": "json",
        }

        headers = {
            "User-Agent": "MVidarr/0.9.8 (https://github.com/prefect421/mvidarr) - Media Library Manager"
        }

        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()  # Raises an exception for bad status codes

            data = response.json()
            results = []

            # OpenSearch returns: [query, [titles], [descriptions], [urls]]
            if len(data) >= 4:
                titles = data[1]
                descriptions = data[2] if len(data) > 2 else []
                urls = data[3] if len(data) > 3 else []

                for i, title in enumerate(titles):
                    results.append(
                        {
                            "name": title,
                            "description": (
                                descriptions[i] if i < len(descriptions) else ""
                            ),
                            "url": (
                                urls[i]
                                if i < len(urls)
                                else f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"
                            ),
                            "source": "wikipedia",
                        }
                    )

            return jsonify({"results": results}), 200

        except requests.RequestException as e:
            logger.error(f"Wikipedia API request failed: {e}")
            return jsonify({"error": f"Wikipedia search failed: {str(e)}"}), 500

    except Exception as e:
        logger.error(f"Failed to search Wikipedia for artist '{artist_name}': {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/search/musicbrainz", methods=["GET"])
@auth_required
def search_musicbrainz():
    """Search MusicBrainz for artist information"""
    try:
        artist_name = request.args.get("artist")
        if not artist_name:
            return jsonify({"error": "artist parameter is required"}), 400

        # Import musicbrainz service
        from src.services.musicbrainz_service import musicbrainz_service

        results = musicbrainz_service.search_artist(artist_name)
        return jsonify({"results": results or []}), 200

    except Exception as e:
        logger.error(f"Failed to search MusicBrainz for artist '{artist_name}': {e}")
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/search/imvdb", methods=["GET"])
@auth_required
def search_imvdb():
    """Search IMVDb for artist information"""
    try:
        artist_name = request.args.get("artist")
        if not artist_name:
            return jsonify({"error": "artist parameter is required"}), 400

        # Import the imvdb service
        from src.services.imvdb_service import imvdb_service

        # Check if IMVDb is properly configured
        if not imvdb_service.api_key:
            return (
                jsonify(
                    {
                        "results": [],
                        "message": "IMVDb API requires authentication. Please configure an API key in Settings.",
                        "authentication_required": True,
                    }
                ),
                200,
            )

        # Use search_artists function which returns a list
        results = imvdb_service.search_artists(artist_name, limit=10)
        if not results:
            return (
                jsonify(
                    {
                        "results": [],
                        "message": "No IMVDb results found or API credentials invalid.",
                        "authentication_required": not bool(imvdb_service.api_key),
                    }
                ),
                200,
            )

        return jsonify({"results": results}), 200

    except Exception as e:
        logger.error(f"Failed to search IMVDb for artist '{artist_name}': {e}")
        # Check if it's an authentication error
        if "API key not configured" in str(e):
            return (
                jsonify(
                    {
                        "results": [],
                        "message": "IMVDb API requires authentication. Please configure an API key in Settings.",
                        "authentication_required": True,
                    }
                ),
                200,
            )
        return jsonify({"error": str(e)}), 500


@metadata_enrichment_bp.route("/auto-match/<int:artist_id>", methods=["GET"])
@auth_required
def auto_match_services(artist_id: int):
    """Automatically match artist to external service IDs"""
    try:
        with get_db() as session:
            artist = session.query(Artist).filter(Artist.id == artist_id).first()

            if not artist:
                return jsonify({"error": "Artist not found"}), 404

            artist_name = artist.name
            logger.info(
                f"Auto-matching services for artist: {artist_name} (ID: {artist_id})"
            )

            matches = {}

            # Search Spotify
            try:
                from src.services.spotify_service import spotify_service

                # Ensure Spotify has access token
                if not spotify_service.access_token:
                    logger.debug(
                        "Spotify access token not available, getting client credentials token"
                    )
                    token_data = spotify_service.get_client_credentials_token()
                    if token_data:
                        spotify_service.access_token = token_data.get("access_token")
                        logger.debug("Spotify client credentials token obtained")
                    else:
                        logger.debug("Failed to get Spotify client credentials token")

                if spotify_service.access_token:
                    logger.debug(
                        f"Spotify access token available, searching for: {artist_name}"
                    )
                    spotify_results = spotify_service.search_artist(
                        artist_name, limit=5
                    )
                    if (
                        spotify_results
                        and "artists" in spotify_results
                        and spotify_results["artists"]["items"]
                    ):
                        best_match = spotify_results["artists"]["items"][0]
                        matches["spotify"] = {
                            "id": best_match.get("id"),
                            "name": best_match.get("name"),
                            "url": best_match.get("external_urls", {}).get("spotify"),
                            "followers": best_match.get("followers", {}).get(
                                "total", 0
                            ),
                            "popularity": best_match.get("popularity", 0),
                        }
                        logger.debug(
                            f"Found Spotify match: {best_match.get('name')} (ID: {best_match.get('id')})"
                        )
                    else:
                        logger.debug(f"No Spotify results found for: {artist_name}")
                else:
                    logger.debug("No Spotify access token available")

            except Exception as e:
                logger.warning(f"Failed to search Spotify for auto-match: {e}")

            # Search Last.fm
            try:
                from src.services.lastfm_service import lastfm_service

                # Refresh credentials before checking
                lastfm_service.refresh_credentials()
                if lastfm_service.api_key:
                    logger.debug(
                        f"Last.fm API key available, searching for: {artist_name}"
                    )
                    lastfm_results = lastfm_service.search_artist(artist_name)
                    if lastfm_results and len(lastfm_results) > 0:
                        best_match = lastfm_results[0]
                        matches["lastfm"] = {
                            "id": best_match.get(
                                "name"
                            ),  # Last.fm uses name as identifier
                            "name": best_match.get("name"),
                            "url": best_match.get("url"),
                            "listeners": best_match.get("listeners", 0),
                            "playcount": best_match.get("playcount", 0),
                        }
                        logger.debug(f"Found Last.fm match: {best_match.get('name')}")
                    else:
                        logger.debug(f"No Last.fm results found for: {artist_name}")
                else:
                    logger.debug("Last.fm API key not configured")

            except Exception as e:
                logger.warning(f"Failed to search Last.fm for auto-match: {e}")

            # Search IMVDb
            try:
                from src.services.imvdb_service import imvdb_service

                # Check API key availability
                api_key = imvdb_service.get_api_key()
                if api_key:
                    logger.info(
                        f"🎵 AUTO-MATCH: IMVDb API key available, searching for: {artist_name}"
                    )
                    imvdb_results = imvdb_service.search_artists(artist_name, limit=5)
                    logger.info(f"🎵 AUTO-MATCH: IMVDb raw results: {imvdb_results}")
                    if imvdb_results and len(imvdb_results) > 0:
                        best_match = imvdb_results[0]
                        logger.info(
                            f"🎵 AUTO-MATCH: IMVDb best match structure: {best_match}"
                        )

                        # Extract artist name from nested structure - more comprehensive approach
                        artist_name_from_result = None

                        # Check all possible nested structures
                        if "entity" in best_match and isinstance(
                            best_match["entity"], dict
                        ):
                            entity = best_match["entity"]
                            logger.info(
                                f"🎵 AUTO-MATCH: IMVDb entity structure: {entity}"
                            )
                            artist_name_from_result = (
                                entity.get("name")
                                or entity.get("slug")
                                or entity.get("title")
                            )

                        # Direct field checks
                        if not artist_name_from_result:
                            artist_name_from_result = (
                                best_match.get("name")
                                or best_match.get("title")
                                or best_match.get("slug")
                            )

                        # Check if there's a url_slug field
                        if not artist_name_from_result:
                            artist_name_from_result = best_match.get("url_slug")

                        # As a last resort, check if there are any string values that might be the name
                        if not artist_name_from_result:
                            for key, value in best_match.items():
                                if (
                                    isinstance(value, str)
                                    and len(value) > 2
                                    and value.lower() != "artist"
                                ):
                                    artist_name_from_result = value
                                    logger.info(
                                        f"🎵 AUTO-MATCH: Using fallback artist name from field '{key}': {value}"
                                    )
                                    break

                        # Build URL
                        url = best_match.get("url")
                        if not url and best_match.get("slug"):
                            url = f"https://imvdb.com/n/{best_match.get('slug')}"
                        elif not url and best_match.get("url_slug"):
                            url = f"https://imvdb.com/n/{best_match.get('url_slug')}"
                        elif not url and best_match.get("id"):
                            url = f"https://imvdb.com/artist/{best_match.get('id')}"

                        matches["imvdb"] = {
                            "id": str(best_match.get("id", "")),
                            "name": artist_name_from_result or artist_name,
                            "url": url,
                            "video_count": best_match.get("video_count", 0),
                            "slug": best_match.get("slug", "")
                            or best_match.get("url_slug", ""),
                        }
                        logger.info(
                            f"🎵 AUTO-MATCH: Final IMVDb match: {artist_name_from_result} (ID: {best_match.get('id')})"
                        )
                    else:
                        logger.info(
                            f"🎵 AUTO-MATCH: No IMVDb results found for: {artist_name}"
                        )
                else:
                    logger.info("🎵 AUTO-MATCH: IMVDb API key not configured")

            except Exception as e:
                logger.warning(f"Failed to search IMVDb for auto-match: {e}")

            # Search MusicBrainz
            try:
                from src.services.musicbrainz_service import musicbrainz_service

                logger.debug(f"MusicBrainz searching for: {artist_name}")
                mb_results = musicbrainz_service.search_artist(artist_name)
                if mb_results and len(mb_results) > 0:
                    best_match = mb_results[0]
                    matches["musicbrainz"] = {
                        "id": best_match.get("mbid"),
                        "mbid": best_match.get(
                            "mbid"
                        ),  # Include both for compatibility
                        "name": best_match.get("name"),
                        "score": best_match.get("confidence", 0),
                        "country": best_match.get("country"),
                        "type": best_match.get("type"),
                    }
                    logger.debug(
                        f"Found MusicBrainz match: {best_match.get('name')} (ID: {best_match.get('mbid')})"
                    )
                else:
                    logger.debug(f"No MusicBrainz results found for: {artist_name}")

            except Exception as e:
                logger.warning(f"Failed to search MusicBrainz for auto-match: {e}")

            # Discogs search removed - service discontinued

            # Search AllMusic (basic web scraping approach)
            try:
                from urllib.parse import quote

                import requests

                logger.debug(f"AllMusic searching for: {artist_name}")
                search_url = (
                    f"https://www.allmusic.com/search/artists/{quote(artist_name)}"
                )
                headers = {
                    "User-Agent": "MVidarr/0.9.8 (https://github.com/prefect421/mvidarr)"
                }

                response = requests.get(search_url, headers=headers, timeout=10)
                if (
                    response.status_code == 200
                    and artist_name.lower() in response.text.lower()
                ):
                    matches["allmusic"] = {
                        "id": artist_name.lower().replace(" ", "-"),
                        "name": artist_name,
                        "url": f"https://www.allmusic.com/artist/{artist_name.lower().replace(' ', '-')}",
                        "source": "allmusic",
                    }
                    logger.debug(f"Found AllMusic match for: {artist_name}")
                else:
                    logger.debug(f"No AllMusic match found for: {artist_name}")

            except Exception as e:
                logger.warning(f"Failed to search AllMusic for auto-match: {e}")

            # Search Wikipedia
            try:
                import requests

                logger.debug(f"Wikipedia searching for: {artist_name}")
                url = "https://en.wikipedia.org/w/api.php"
                params = {
                    "action": "opensearch",
                    "search": artist_name,
                    "limit": 5,
                    "namespace": 0,
                    "format": "json",
                }
                headers = {
                    "User-Agent": "MVidarr/0.9.8 (https://github.com/prefect421/mvidarr) - Media Library Manager"
                }

                response = requests.get(url, params=params, headers=headers, timeout=10)
                response.raise_for_status()

                data = response.json()
                if len(data) >= 4 and data[1]:  # Check if titles exist
                    titles = data[1]
                    urls = data[3] if len(data) > 3 else []

                    if titles and len(titles) > 0:
                        best_title = titles[0]
                        best_url = (
                            urls[0]
                            if urls
                            else f"https://en.wikipedia.org/wiki/{best_title.replace(' ', '_')}"
                        )

                        matches["wikipedia"] = {
                            "id": best_title.replace(" ", "_"),
                            "name": best_title,
                            "url": best_url,
                            "source": "wikipedia",
                        }
                        logger.debug(f"Found Wikipedia match: {best_title}")
                    else:
                        logger.debug(f"No Wikipedia results found for: {artist_name}")
                else:
                    logger.debug(f"No Wikipedia results found for: {artist_name}")

            except Exception as e:
                logger.warning(f"Failed to search Wikipedia for auto-match: {e}")

            # Count successful matches
            match_count = len(matches)

            return (
                jsonify(
                    {
                        "success": True,
                        "artist_id": artist_id,
                        "artist_name": artist_name,
                        "matches": matches,
                        "match_count": match_count,
                        "message": f"Found {match_count} service matches for {artist_name}",
                    }
                ),
                200,
            )

    except Exception as e:
        logger.error(f"Failed to auto-match services for artist {artist_id}: {e}")
        return jsonify({"error": str(e)}), 500
