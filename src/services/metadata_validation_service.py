"""
Metadata Validation and Automation Service for MVidarr 0.9.7 - Issue #75
Automated validation and quality control for artist metadata enrichment.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import desc, or_
from src.database.connection import get_db
from src.database.models import Artist, Video
from src.services.metadata_enrichment_service import metadata_enrichment_service
from src.services.settings_service import settings
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.metadata_validation")


@dataclass
class ValidationResult:
    """Result of metadata validation"""

    artist_id: int
    is_valid: bool
    confidence_score: float = 0.0
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    data_quality_score: float = 0.0
    needs_enrichment: bool = False


@dataclass
class AutomationStats:
    """Statistics for automation runs"""

    run_date: datetime
    candidates_found: int
    enriched_count: int
    validation_failures: int
    avg_confidence_improvement: float = 0.0
    total_processing_time: float = 0.0


class MetadataValidationService:
    """Service for automated metadata validation and enrichment"""

    def __init__(self):
        self.enrichment_service = metadata_enrichment_service

        # Validation thresholds - made more lenient for better user experience
        self.min_confidence_threshold = 0.5  # Reduced from 0.7
        self.min_data_quality_score = 0.4  # Reduced from 0.6
        self.max_metadata_age_days = 90  # Increased from 30

        # Automation settings
        self.batch_size = 20
        self.rate_limit_delay = 0.5  # seconds between enrichments
        self.max_daily_enrichments = 100

        # Quality scoring weights - rebalanced for better scoring
        self.quality_weights = {
            "external_ids": 0.35,  # Has Spotify, Last.fm, IMVDb IDs - most important
            "metadata_richness": 0.35,  # Has genres, bio, images, etc. - equally important
            "metadata_freshness": 0.10,  # How recent the metadata is - less critical
            "confidence_score": 0.20,  # Confidence from enrichment process - moderate importance
        }

    def validate_artist_metadata(self, artist_id: int) -> ValidationResult:
        """Validate metadata quality for a specific artist"""
        try:
            with get_db() as session:
                artist = session.query(Artist).filter(Artist.id == artist_id).first()

                if not artist:
                    return ValidationResult(
                        artist_id=artist_id,
                        is_valid=False,
                        issues=["Artist not found"],
                        needs_enrichment=False,
                    )

                # Eagerly load all needed data to avoid session issues
                artist_data = {
                    "id": artist.id,
                    "name": artist.name,
                    "spotify_id": artist.spotify_id,
                    "lastfm_name": artist.lastfm_name,
                    "imvdb_id": artist.imvdb_id,
                    "genres": artist.genres,
                    "imvdb_metadata": artist.imvdb_metadata,
                    "created_at": artist.created_at,
                    "updated_at": artist.updated_at,
                }

                result = ValidationResult(artist_id=artist_id, is_valid=True)

                # Check external IDs coverage
                try:
                    external_ids_score = self._validate_external_ids(
                        artist_data, result
                    )
                except Exception as e:
                    logger.error(
                        f"Error in _validate_external_ids for artist {artist_id}: {e}"
                    )
                    external_ids_score = 0.0

                # Check metadata richness
                try:
                    richness_score = self._validate_metadata_richness(
                        artist_data, result
                    )
                except Exception as e:
                    logger.error(
                        f"Error in _validate_metadata_richness for artist {artist_id}: {e}"
                    )
                    richness_score = 0.0

                # Check metadata freshness
                try:
                    freshness_score = self._validate_metadata_freshness(
                        artist_data, result
                    )
                except Exception as e:
                    logger.error(
                        f"Error in _validate_metadata_freshness for artist {artist_id}: {e}"
                    )
                    freshness_score = 0.0

                # Check enrichment confidence
                try:
                    confidence_score = self._validate_enrichment_confidence(
                        artist_data, result
                    )
                except Exception as e:
                    logger.error(
                        f"Error in _validate_enrichment_confidence for artist {artist_id}: {e}"
                    )
                    confidence_score = 0.0

                # Calculate overall data quality score
                try:
                    result.data_quality_score = (
                        external_ids_score * self.quality_weights["external_ids"]
                        + richness_score * self.quality_weights["metadata_richness"]
                        + freshness_score * self.quality_weights["metadata_freshness"]
                        + confidence_score * self.quality_weights["confidence_score"]
                    )
                except Exception as e:
                    logger.error(
                        f"Error calculating data quality score for artist {artist_id}: {e}"
                    )
                    result.data_quality_score = 0.0

                # Determine if validation passes
                result.is_valid = (
                    result.data_quality_score >= self.min_data_quality_score
                    and len(
                        [
                            issue
                            for issue in result.issues
                            if issue.startswith("Critical")
                        ]
                    )
                    == 0
                )

                # Determine if enrichment is needed
                result.needs_enrichment = (
                    result.data_quality_score < self.min_data_quality_score
                    or confidence_score < self.min_confidence_threshold
                    or freshness_score < 0.5
                )

                return result

        except Exception as e:
            logger.error(f"Error validating metadata for artist {artist_id}: {e}")
            return ValidationResult(
                artist_id=artist_id,
                is_valid=False,
                issues=[f"Validation error: {str(e)}"],
                needs_enrichment=True,
            )

    def _validate_external_ids(
        self, artist_data: Dict, result: ValidationResult
    ) -> float:
        """Validate external ID coverage"""
        score = 0.0
        total_sources = 3  # Spotify, Last.fm, IMVDb

        if artist_data.get("spotify_id"):
            score += 1 / total_sources
        else:
            result.issues.append("Missing Spotify ID")
            result.recommendations.append("Link artist to Spotify for better metadata")

        if artist_data.get("lastfm_name"):
            score += 1 / total_sources
        else:
            result.issues.append("Missing Last.fm name")
            result.recommendations.append("Add Last.fm integration for listening data")

        if artist_data.get("imvdb_id"):
            score += 1 / total_sources
        else:
            result.issues.append("Missing IMVDb ID")
            result.recommendations.append("Search IMVDb for music videos")

        return score

    def _validate_metadata_richness(
        self, artist_data: Dict, result: ValidationResult
    ) -> float:
        """Validate metadata richness and completeness"""
        score = 0.0
        total_fields = 6

        # Check for genres - this can exist independently of enriched metadata
        if artist_data.get("genres") and artist_data.get("genres", "").strip():
            score += 1 / total_fields
        else:
            result.issues.append("Missing genre information")
            result.recommendations.append(
                "Enrich metadata to get genre classifications"
            )

        # Check for enriched metadata - handle None and empty dict cases properly
        enriched_data = artist_data.get("imvdb_metadata") or {}

        if not enriched_data:
            result.issues.append("No enriched metadata found")
            result.recommendations.append(
                "Run metadata enrichment to populate missing data"
            )
            # Still allow partial score for genres if present
            return score

        # Only mark as critical if we have some metadata but it's incomplete
        has_any_enriched_data = False

        # Biography
        if enriched_data.get("biography"):
            score += 1 / total_fields
            has_any_enriched_data = True
        else:
            result.recommendations.append("Add artist biography from Last.fm")

        # Images
        if enriched_data.get("images"):
            score += 1 / total_fields
            has_any_enriched_data = True
        else:
            result.recommendations.append("Add artist images from Spotify")

        # Related artists
        if enriched_data.get("related_artists"):
            score += 1 / total_fields
            has_any_enriched_data = True
        else:
            result.recommendations.append("Add related artists for discovery")

        # Popularity metrics
        if enriched_data.get("popularity") or enriched_data.get("followers"):
            score += 1 / total_fields
            has_any_enriched_data = True
        else:
            result.recommendations.append("Add popularity metrics from Spotify")

        # Listening stats
        if enriched_data.get("playcount") or enriched_data.get("listeners"):
            score += 1 / total_fields
            has_any_enriched_data = True
        else:
            result.recommendations.append("Add listening statistics from Last.fm")

        return score

    def get_blank_metadata_report(self, artist_id: int) -> Dict:
        """Generate detailed report of blank/missing metadata fields for specific artist"""
        try:
            with get_db() as session:
                artist = session.query(Artist).filter(Artist.id == artist_id).first()

                if not artist:
                    return {"error": "Artist not found"}

                # Core fields to check
                blank_fields = []
                recommendations = []

                # Check basic artist fields
                if not artist.genres or not artist.genres.strip():
                    blank_fields.append(
                        {
                            "field": "genres",
                            "description": "Music genres for categorization",
                            "priority": "high",
                            "action": "Add genres manually or run enrichment",
                        }
                    )

                # Check external service IDs
                if not artist.spotify_id:
                    blank_fields.append(
                        {
                            "field": "spotify_id",
                            "description": "Spotify artist ID for enhanced metadata",
                            "priority": "high",
                            "action": "Link artist to Spotify via enrichment",
                        }
                    )

                if not artist.lastfm_name:
                    blank_fields.append(
                        {
                            "field": "lastfm_name",
                            "description": "Last.fm artist name for biography and stats",
                            "priority": "medium",
                            "action": "Link artist to Last.fm via enrichment",
                        }
                    )

                if not artist.imvdb_id:
                    blank_fields.append(
                        {
                            "field": "imvdb_id",
                            "description": "IMVDb ID for video database integration",
                            "priority": "medium",
                            "action": "Link artist to IMVDb via video discovery",
                        }
                    )

                # Check enriched metadata
                enriched_data = artist.imvdb_metadata or {}

                if not enriched_data.get("biography"):
                    blank_fields.append(
                        {
                            "field": "biography",
                            "description": "Artist biography and background information",
                            "priority": "medium",
                            "action": "Run Last.fm enrichment to get biography",
                        }
                    )

                if not enriched_data.get("images"):
                    blank_fields.append(
                        {
                            "field": "images",
                            "description": "Artist images and photos",
                            "priority": "low",
                            "action": "Run Spotify enrichment to get artist images",
                        }
                    )

                if not enriched_data.get("related_artists"):
                    blank_fields.append(
                        {
                            "field": "related_artists",
                            "description": "Related artists for music discovery",
                            "priority": "low",
                            "action": "Run Spotify enrichment to get related artists",
                        }
                    )

                # Calculate completion percentage
                total_fields = 7  # Total important fields we're checking
                missing_count = len(blank_fields)
                completion_percentage = (
                    (total_fields - missing_count) / total_fields
                ) * 100

                return {
                    "success": True,
                    "artist_name": artist.name,
                    "completion_percentage": round(completion_percentage, 1),
                    "missing_fields_count": missing_count,
                    "blank_fields": blank_fields,
                    "next_steps": [
                        "Click 'Enrich Metadata' to automatically fill missing fields",
                        "Manually add genres and biography if enrichment doesn't find them",
                        "Link to external services via the External Services section",
                    ],
                }

        except Exception as e:
            logger.error(
                f"Error generating blank metadata report for artist {artist_id}: {e}"
            )
            return {"error": f"Failed to generate report: {str(e)}"}

    def _validate_metadata_freshness(
        self, artist_data: Dict, result: ValidationResult
    ) -> float:
        """Validate metadata freshness"""
        # Handle None metadata case gracefully
        enriched_data = artist_data.get("imvdb_metadata") or {}

        if not enriched_data:
            result.issues.append("No metadata available for freshness check")
            return 0.5  # Neutral score instead of 0 - not having metadata isn't necessarily bad

        enrichment_date_str = enriched_data.get("enrichment_date")
        if not enrichment_date_str:
            result.issues.append("No enrichment date found")
            return 0.3  # Slightly better than 0 - we have metadata but no timestamp

        try:
            enrichment_date = datetime.fromisoformat(enrichment_date_str)
            age_days = (datetime.now() - enrichment_date).days

            if age_days > self.max_metadata_age_days:
                result.issues.append(
                    f"Metadata is {age_days} days old (threshold: {self.max_metadata_age_days})"
                )
                result.recommendations.append(
                    "Refresh metadata to get latest information"
                )
                # Graceful degradation - don't go completely to 0
                return max(0.1, 1.0 - (age_days / (self.max_metadata_age_days * 2)))
            else:
                return 1.0

        except (ValueError, TypeError):
            result.issues.append("Invalid enrichment date format")
            return 0.2  # Better than 0 - we have a date field, just malformed

    def _validate_enrichment_confidence(
        self, artist_data: Dict, result: ValidationResult
    ) -> float:
        """Validate enrichment confidence score"""
        # Handle None metadata case gracefully
        enriched_data = artist_data.get("imvdb_metadata") or {}

        if not enriched_data:
            result.confidence_score = 0.0
            return 0.5  # Neutral score - no confidence data available

        confidence = enriched_data.get("confidence_score", 0.0)
        result.confidence_score = confidence

        if confidence < self.min_confidence_threshold:
            result.issues.append(
                f"Low confidence score: {confidence:.2f} (threshold: {self.min_confidence_threshold})"
            )
            result.recommendations.append("Re-run enrichment with additional sources")

        return confidence

    async def auto_enrich_candidates(self, limit: int = None) -> AutomationStats:
        """Automatically enrich artists that need metadata enrichment"""
        start_time = datetime.now()
        limit = limit or self.batch_size

        try:
            # Find candidates for enrichment
            candidates = self._find_enrichment_candidates(limit)

            stats = AutomationStats(
                run_date=start_time,
                candidates_found=len(candidates),
                enriched_count=0,
                validation_failures=0,
            )

            if not candidates:
                logger.info("No candidates found for automated enrichment")
                return stats

            logger.info(f"Starting automated enrichment for {len(candidates)} artists")

            confidence_before = []
            confidence_after = []

            # Process each candidate
            for artist_id in candidates:
                try:
                    # Validate before enrichment
                    validation_before = self.validate_artist_metadata(artist_id)
                    confidence_before.append(validation_before.confidence_score)

                    # Run enrichment
                    enrichment_result = (
                        await self.enrichment_service.enrich_artist_metadata(
                            artist_id, force_refresh=True
                        )
                    )

                    if enrichment_result.success:
                        # Validate after enrichment
                        validation_after = self.validate_artist_metadata(artist_id)
                        confidence_after.append(validation_after.confidence_score)

                        if validation_after.is_valid:
                            stats.enriched_count += 1
                            logger.info(f"Successfully enriched artist {artist_id}")
                        else:
                            stats.validation_failures += 1
                            logger.warning(
                                f"Enrichment succeeded but validation failed for artist {artist_id}"
                            )
                    else:
                        stats.validation_failures += 1
                        logger.warning(
                            f"Enrichment failed for artist {artist_id}: {enrichment_result.errors}"
                        )

                    # Rate limiting
                    await asyncio.sleep(self.rate_limit_delay)

                except Exception as e:
                    stats.validation_failures += 1
                    logger.error(f"Error processing artist {artist_id}: {e}")

            # Calculate improvement statistics
            if confidence_before and confidence_after:
                avg_before = sum(confidence_before) / len(confidence_before)
                avg_after = sum(confidence_after) / len(confidence_after)
                stats.avg_confidence_improvement = avg_after - avg_before

            stats.total_processing_time = (datetime.now() - start_time).total_seconds()

            logger.info(
                f"Automated enrichment completed: {stats.enriched_count}/{stats.candidates_found} successful"
            )
            return stats

        except Exception as e:
            logger.error(f"Error in automated enrichment: {e}")
            return AutomationStats(
                run_date=start_time,
                candidates_found=0,
                enriched_count=0,
                validation_failures=1,
            )

    def _find_enrichment_candidates(self, limit: int) -> List[int]:
        """Find artists that are candidates for metadata enrichment"""
        try:
            with get_db() as session:
                # Build query for artists needing enrichment
                query = session.query(Artist.id)

                # Artists with missing external IDs
                missing_ids_condition = or_(
                    Artist.spotify_id.is_(None),
                    Artist.lastfm_name.is_(None),
                    Artist.imvdb_id.is_(None),
                )

                # Artists with no enriched metadata
                no_metadata_condition = or_(
                    Artist.imvdb_metadata.is_(None), Artist.imvdb_metadata == {}
                )

                # Artists with old metadata
                cutoff_date = datetime.now() - timedelta(
                    days=self.max_metadata_age_days
                )
                old_metadata_condition = Artist.updated_at < cutoff_date

                # Combine conditions
                query = query.filter(
                    or_(
                        missing_ids_condition,
                        no_metadata_condition,
                        old_metadata_condition,
                    )
                )

                # Order by priority (artists with videos first, then by oldest update)
                query = query.join(Video, Artist.id == Video.artist_id, isouter=True)
                query = query.order_by(
                    desc(Video.id.isnot(None)),  # Artists with videos first
                    Artist.updated_at.asc(),  # Oldest first
                )

                # Apply limit and get results
                candidates = query.limit(limit).all()
                return [candidate.id for candidate in candidates]

        except Exception as e:
            logger.error(f"Error finding enrichment candidates: {e}")
            return []

    def get_validation_report(self, limit: int = 100) -> Dict:
        """Generate a validation report for artists"""
        try:
            with get_db() as session:
                # Get sample of artists
                artists = (
                    session.query(Artist).order_by(Artist.id.desc()).limit(limit).all()
                )

                # Extract all artist data upfront to avoid session issues
                artists_data = []
                for artist in artists:
                    try:
                        artist_info = {
                            "id": artist.id,
                            "name": artist.name,
                        }
                        artists_data.append(artist_info)
                    except Exception as e:
                        logger.error(f"Error extracting artist data: {e}")
                        continue

                validation_results = []
                quality_scores = []
                issues_summary = {}

                for artist_info in artists_data:
                    try:
                        # Use pre-extracted artist data to avoid session issues
                        artist_data = {
                            "artist_id": artist_info["id"],
                            "artist_name": artist_info["name"],
                        }

                        logger.info(
                            f"Processing validation for artist {artist_info['id']}: {artist_info['name']}"
                        )
                        validation = self.validate_artist_metadata(artist_info["id"])
                        validation_results.append(
                            {
                                **artist_data,
                                "is_valid": validation.is_valid,
                                "quality_score": validation.data_quality_score,
                                "confidence_score": validation.confidence_score,
                                "needs_enrichment": validation.needs_enrichment,
                                "issues_count": len(validation.issues),
                                "recommendations_count": len(
                                    validation.recommendations
                                ),
                            }
                        )
                        quality_scores.append(validation.data_quality_score)

                        # Count issues
                        for issue in validation.issues:
                            issue_type = issue.split(":")[0] if ":" in issue else issue
                            issues_summary[issue_type] = (
                                issues_summary.get(issue_type, 0) + 1
                            )

                    except Exception as e:
                        logger.error(
                            f"Error processing validation for artist {artist_info['id']}: {e}"
                        )
                        # Add a default failed validation result
                        validation_results.append(
                            {
                                "artist_id": artist_info["id"],
                                "artist_name": artist_info["name"],
                                "is_valid": False,
                                "quality_score": 0.0,
                                "confidence_score": 0.0,
                                "needs_enrichment": True,
                                "issues_count": 1,
                                "recommendations_count": 1,
                            }
                        )
                        quality_scores.append(0.0)
                        # Add a generic issue for failed validation
                        issues_summary["Validation Error"] = (
                            issues_summary.get("Validation Error", 0) + 1
                        )

                # Calculate statistics
                total_artists = len(validation_results)
                valid_artists = len([r for r in validation_results if r["is_valid"]])
                needs_enrichment = len(
                    [r for r in validation_results if r["needs_enrichment"]]
                )
                avg_quality_score = (
                    sum(quality_scores) / len(quality_scores) if quality_scores else 0
                )

                return {
                    "summary": {
                        "total_artists_checked": total_artists,
                        "valid_artists": valid_artists,
                        "validation_pass_rate": (
                            round(valid_artists / total_artists * 100, 1)
                            if total_artists > 0
                            else 0
                        ),
                        "artists_needing_enrichment": needs_enrichment,
                        "average_quality_score": round(avg_quality_score, 2),
                    },
                    "issues_summary": issues_summary,
                    "validation_results": validation_results,
                    "report_date": datetime.now().isoformat(),
                }

        except Exception as e:
            logger.error(f"Error generating validation report: {e}")
            return {"error": str(e), "report_date": datetime.now().isoformat()}

    def schedule_auto_enrichment(self) -> bool:
        """Schedule automated enrichment to run"""
        try:
            # Check if we've hit daily limits
            daily_limit = settings.get(
                "metadata_enrichment_daily_limit", self.max_daily_enrichments
            )

            # This would typically be called by a scheduler
            # For now, just run a small batch
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                stats = loop.run_until_complete(self.auto_enrich_candidates(limit=10))
                logger.info(
                    f"Scheduled enrichment completed: {stats.enriched_count} artists processed"
                )
                return stats.enriched_count > 0
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"Error in scheduled auto enrichment: {e}")
            return False


# Global instance
metadata_validation_service = MetadataValidationService()
