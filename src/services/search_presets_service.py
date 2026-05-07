"""
Search Presets Management Service for MVidarr 0.9.7 - Issue #73
Handles saved search presets, suggestions, and user search preferences.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session
from src.database.connection import get_db
from src.database.models import User
from src.database.search_models import (
    SearchAnalytics,
    SearchAnalyticsEvent,
    SearchPreset,
    SearchPresetType,
)
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.search_presets")


class SearchPresetsService:
    """Service for managing saved search presets and user preferences"""

    def create_preset(
        self,
        user_id: int,
        name: str,
        search_criteria: Dict[str, Any],
        description: str = None,
        is_public: bool = False,
        is_favorite: bool = False,
    ) -> SearchPreset:
        """
        Create a new search preset for a user

        Args:
            user_id: ID of the user creating the preset
            name: Display name for the preset
            search_criteria: Dictionary containing search parameters
            description: Optional description of the preset
            is_public: Whether other users can see/use this preset
            is_favorite: Whether this is a user's favorite preset

        Returns:
            Created SearchPreset instance
        """
        try:
            with get_db() as db:
                # Validate that user exists
                user = db.query(User).filter(User.id == user_id).first()
                if not user:
                    raise ValueError(f"User with ID {user_id} not found")

                # Check for duplicate names for this user
                existing = (
                    db.query(SearchPreset)
                    .filter(
                        and_(SearchPreset.user_id == user_id, SearchPreset.name == name)
                    )
                    .first()
                )

                if existing:
                    raise ValueError(
                        f"Preset with name '{name}' already exists for this user"
                    )

                # If this is being set as favorite, unset any existing favorites
                if is_favorite:
                    db.query(SearchPreset).filter(
                        and_(
                            SearchPreset.user_id == user_id,
                            SearchPreset.is_favorite == True,
                        )
                    ).update({SearchPreset.is_favorite: False})

                # Create the preset
                preset = SearchPreset(
                    user_id=user_id,
                    name=name,
                    description=description,
                    search_criteria=search_criteria,
                    preset_type=SearchPresetType.USER_DEFINED,
                    is_public=is_public,
                    is_favorite=is_favorite,
                )

                db.add(preset)
                db.commit()
                db.refresh(preset)

                # Track analytics event
                self._track_preset_event(
                    db=db,
                    user_id=user_id,
                    event_type=SearchAnalyticsEvent.PRESET_CREATED,
                    preset_id=preset.id,
                    event_metadata={"preset_name": name, "is_public": is_public},
                )

                logger.info(f"Created search preset '{name}' for user {user_id}")
                return preset

        except Exception as e:
            logger.error(f"Error creating search preset: {str(e)}")
            raise

    def get_user_presets(
        self, user_id: int, include_public: bool = True, include_system: bool = True
    ) -> List[SearchPreset]:
        """
        Get all search presets available to a user

        Args:
            user_id: ID of the user
            include_public: Whether to include public presets from other users
            include_system: Whether to include system-defined presets

        Returns:
            List of SearchPreset instances
        """
        try:
            with get_db() as db:
                # Start with user's own presets
                query = db.query(SearchPreset).filter(SearchPreset.user_id == user_id)

                # Add public presets from other users if requested
                if include_public:
                    public_query = db.query(SearchPreset).filter(
                        and_(
                            SearchPreset.user_id != user_id,
                            SearchPreset.is_public == True,
                        )
                    )
                    query = query.union(public_query)

                # Add system presets if requested
                if include_system:
                    system_query = db.query(SearchPreset).filter(
                        SearchPreset.preset_type == SearchPresetType.SYSTEM
                    )
                    query = query.union(system_query)

                # Order by favorites first, then usage count, then name
                presets = query.order_by(
                    desc(SearchPreset.is_favorite),
                    desc(SearchPreset.usage_count),
                    SearchPreset.name,
                ).all()

                return presets

        except Exception as e:
            logger.error(f"Error getting user presets: {str(e)}")
            raise

    def update_preset(
        self,
        preset_id: int,
        user_id: int,
        name: str = None,
        search_criteria: Dict[str, Any] = None,
        description: str = None,
        is_public: bool = None,
        is_favorite: bool = None,
    ) -> SearchPreset:
        """
        Update an existing search preset

        Args:
            preset_id: ID of the preset to update
            user_id: ID of the user (for authorization)
            name: New name for the preset
            search_criteria: New search criteria
            description: New description
            is_public: New public status
            is_favorite: New favorite status

        Returns:
            Updated SearchPreset instance
        """
        try:
            with get_db() as db:
                # Get the preset and verify ownership
                preset = (
                    db.query(SearchPreset)
                    .filter(
                        and_(
                            SearchPreset.id == preset_id,
                            SearchPreset.user_id == user_id,
                        )
                    )
                    .first()
                )

                if not preset:
                    raise ValueError(
                        f"Preset with ID {preset_id} not found or not owned by user {user_id}"
                    )

                # Update fields if provided
                if name is not None:
                    # Check for duplicate names
                    existing = (
                        db.query(SearchPreset)
                        .filter(
                            and_(
                                SearchPreset.user_id == user_id,
                                SearchPreset.name == name,
                                SearchPreset.id != preset_id,
                            )
                        )
                        .first()
                    )

                    if existing:
                        raise ValueError(
                            f"Preset with name '{name}' already exists for this user"
                        )

                    preset.name = name

                if search_criteria is not None:
                    preset.search_criteria = search_criteria

                if description is not None:
                    preset.description = description

                if is_public is not None:
                    preset.is_public = is_public

                if is_favorite is not None:
                    if is_favorite:
                        # Unset any existing favorites for this user
                        db.query(SearchPreset).filter(
                            and_(
                                SearchPreset.user_id == user_id,
                                SearchPreset.is_favorite == True,
                                SearchPreset.id != preset_id,
                            )
                        ).update({SearchPreset.is_favorite: False})

                    preset.is_favorite = is_favorite

                preset.updated_at = datetime.utcnow()

                db.commit()
                db.refresh(preset)

                # Track analytics event
                self._track_preset_event(
                    db=db,
                    user_id=user_id,
                    event_type=SearchAnalyticsEvent.PRESET_MODIFIED,
                    preset_id=preset.id,
                    event_metadata={"preset_name": preset.name},
                )

                logger.info(f"Updated search preset {preset_id} for user {user_id}")
                return preset

        except Exception as e:
            logger.error(f"Error updating search preset: {str(e)}")
            raise

    def delete_preset(self, preset_id: int, user_id: int) -> bool:
        """
        Delete a search preset

        Args:
            preset_id: ID of the preset to delete
            user_id: ID of the user (for authorization)

        Returns:
            True if deleted successfully
        """
        try:
            with get_db() as db:
                # Get the preset and verify ownership
                preset = (
                    db.query(SearchPreset)
                    .filter(
                        and_(
                            SearchPreset.id == preset_id,
                            SearchPreset.user_id == user_id,
                        )
                    )
                    .first()
                )

                if not preset:
                    raise ValueError(
                        f"Preset with ID {preset_id} not found or not owned by user {user_id}"
                    )

                # Don't allow deletion of system presets
                if preset.preset_type == SearchPresetType.SYSTEM:
                    raise ValueError("System presets cannot be deleted")

                preset_name = preset.name

                db.delete(preset)
                db.commit()

                logger.info(
                    f"Deleted search preset '{preset_name}' (ID: {preset_id}) for user {user_id}"
                )
                return True

        except Exception as e:
            logger.error(f"Error deleting search preset: {str(e)}")
            raise

    def use_preset(self, preset_id: int, user_id: int = None) -> SearchPreset:
        """
        Mark a preset as used and update usage statistics

        Args:
            preset_id: ID of the preset being used
            user_id: ID of the user using the preset (optional)

        Returns:
            The used SearchPreset instance
        """
        try:
            with get_db() as db:
                preset = (
                    db.query(SearchPreset).filter(SearchPreset.id == preset_id).first()
                )

                if not preset:
                    raise ValueError(f"Preset with ID {preset_id} not found")

                # Check if user has access to this preset
                if (
                    user_id
                    and preset.user_id != user_id
                    and not preset.is_public
                    and preset.preset_type != SearchPresetType.SYSTEM
                ):
                    raise ValueError(
                        f"User {user_id} does not have access to preset {preset_id}"
                    )

                # Update usage statistics
                preset.increment_usage()

                db.commit()
                db.refresh(preset)

                # Track analytics event
                if user_id:
                    self._track_preset_event(
                        db=db,
                        user_id=user_id,
                        event_type=SearchAnalyticsEvent.PRESET_USED,
                        preset_id=preset.id,
                        event_metadata={"preset_name": preset.name},
                    )

                logger.debug(f"Preset {preset_id} used by user {user_id}")
                return preset

        except Exception as e:
            logger.error(f"Error using preset: {str(e)}")
            raise

    def get_preset_by_id(
        self, preset_id: int, user_id: int = None
    ) -> Optional[SearchPreset]:
        """
        Get a specific preset by ID with access control

        Args:
            preset_id: ID of the preset
            user_id: ID of the user requesting the preset (for access control)

        Returns:
            SearchPreset instance if found and accessible, None otherwise
        """
        try:
            with get_db() as db:
                preset = (
                    db.query(SearchPreset).filter(SearchPreset.id == preset_id).first()
                )

                if not preset:
                    return None

                # Check access permissions
                if user_id:
                    # User can access their own presets, public presets, or system presets
                    if (
                        preset.user_id == user_id
                        or preset.is_public
                        or preset.preset_type == SearchPresetType.SYSTEM
                    ):
                        return preset
                    else:
                        return None
                else:
                    # Without user_id, only allow public and system presets
                    if (
                        preset.is_public
                        or preset.preset_type == SearchPresetType.SYSTEM
                    ):
                        return preset
                    else:
                        return None

        except Exception as e:
            logger.error(f"Error getting preset by ID: {str(e)}")
            return None

    def create_system_presets(self) -> List[SearchPreset]:
        """
        Create default system presets for common search scenarios

        Returns:
            List of created system presets
        """
        system_presets = [
            {
                "name": "Recently Added",
                "description": "Videos added in the last 7 days",
                "search_criteria": {
                    "created_after": (
                        datetime.utcnow() - timedelta(days=7)
                    ).isoformat(),
                    "sort_by": "created_at",
                    "sort_order": "desc",
                },
            },
            {
                "name": "High Quality Videos",
                "description": "Videos in 1080p or higher quality",
                "search_criteria": {
                    "quality": ["1080p", "1440p", "2160p", "4K"],
                    "sort_by": "quality",
                    "sort_order": "desc",
                },
            },
            {
                "name": "Downloaded Videos",
                "description": "All downloaded videos",
                "search_criteria": {
                    "status": ["DOWNLOADED"],
                    "sort_by": "created_at",
                    "sort_order": "desc",
                },
            },
            {
                "name": "Wanted Videos",
                "description": "Videos marked as wanted but not yet downloaded",
                "search_criteria": {
                    "status": ["WANTED"],
                    "sort_by": "created_at",
                    "sort_order": "desc",
                },
            },
            {
                "name": "Recent Music Videos",
                "description": "Music videos from the last 3 years",
                "search_criteria": {
                    "year_range": {
                        "min": datetime.utcnow().year - 3,
                        "max": datetime.utcnow().year,
                    },
                    "sort_by": "year",
                    "sort_order": "desc",
                },
            },
            {
                "name": "Videos with Thumbnails",
                "description": "Videos that have thumbnail images",
                "search_criteria": {
                    "has_thumbnail": True,
                    "sort_by": "created_at",
                    "sort_order": "desc",
                },
            },
            {
                "name": "Long Format Videos",
                "description": "Videos longer than 5 minutes",
                "search_criteria": {
                    "duration_range": {"min": 300},  # 5 minutes in seconds
                    "sort_by": "duration",
                    "sort_order": "desc",
                },
            },
        ]

        created_presets = []

        try:
            with get_db() as db:
                for preset_data in system_presets:
                    # Check if system preset already exists
                    existing = (
                        db.query(SearchPreset)
                        .filter(
                            and_(
                                SearchPreset.name == preset_data["name"],
                                SearchPreset.preset_type == SearchPresetType.SYSTEM,
                            )
                        )
                        .first()
                    )

                    if not existing:
                        preset = SearchPreset(
                            user_id=None,  # System presets have no user
                            name=preset_data["name"],
                            description=preset_data["description"],
                            search_criteria=preset_data["search_criteria"],
                            preset_type=SearchPresetType.SYSTEM,
                            is_public=True,  # System presets are always public
                        )

                        db.add(preset)
                        created_presets.append(preset)

                if created_presets:
                    db.commit()
                    logger.info(f"Created {len(created_presets)} system search presets")

                return created_presets

        except Exception as e:
            logger.error(f"Error creating system presets: {str(e)}")
            raise

    def get_popular_presets(self, limit: int = 10) -> List[SearchPreset]:
        """
        Get most popular public presets based on usage

        Args:
            limit: Maximum number of presets to return

        Returns:
            List of popular SearchPreset instances
        """
        try:
            with get_db() as db:
                presets = (
                    db.query(SearchPreset)
                    .filter(SearchPreset.is_public == True)
                    .order_by(
                        desc(SearchPreset.usage_count), desc(SearchPreset.last_used_at)
                    )
                    .limit(limit)
                    .all()
                )

                return presets

        except Exception as e:
            logger.error(f"Error getting popular presets: {str(e)}")
            return []

    def _track_preset_event(
        self,
        db: Session,
        user_id: int,
        event_type: SearchAnalyticsEvent,
        preset_id: int = None,
        event_metadata: Dict[str, Any] = None,
    ):
        """Track preset-related analytics events"""
        try:
            analytics_event = SearchAnalytics(
                user_id=user_id,
                event_type=event_type,
                preset_id=preset_id,
                metadata=event_metadata,
            )

            db.add(analytics_event)
            # Note: commit is handled by the calling method

        except Exception as e:
            logger.error(f"Error tracking preset analytics: {str(e)}")


# Initialize service instance
search_presets_service = SearchPresetsService()
