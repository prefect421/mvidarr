"""
FastAPI Theme Management Router
Migrated from Flask src/api/themes.py
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi import Path as FastAPIPath
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from src.database.connection import get_db_session
from src.database.models import CustomTheme

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/themes",
    tags=["themes"],
    responses={
        404: {"description": "Theme not found"},
        422: {"description": "Validation error"},
    },
)

from src.api.fastapi.auth_dependencies import (
    get_current_user,
    require_authentication,
)

# Use proper authentication dependencies
# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class ThemeData(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = ""
    theme_data: Optional[Dict[str, Any]] = None
    light_theme_data: Optional[Dict[str, Any]] = None
    is_public: bool = True


class ThemeResponse(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str]
    is_built_in: bool
    is_public: bool
    theme_data: Optional[Dict[str, Any]]
    light_theme_data: Optional[Dict[str, Any]]
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ApplyThemeRequest(BaseModel):
    theme_name: str


# ========================================================================================
# UTILITY FUNCTIONS (MIGRATED FROM FLASK)
# ========================================================================================


# Hardcoded theme functions removed - all themes now stored in database


# Hardcoded theme functions removed - all themes now stored in database


# ========================================================================================
# THEME MANAGEMENT ENDPOINTS
# ========================================================================================


@router.get("")
async def get_themes(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get all available themes (built-in and custom)"""
    try:
        user_id = current_user.get("user_id", 6)
        logger.info(f"Loading themes for user {user_id}")

        # Get custom themes from database
        try:
            themes = (
                session.query(CustomTheme)
                .filter(
                    or_(
                        CustomTheme.is_public == True,
                        CustomTheme.is_built_in == True,
                        CustomTheme.created_by == user_id,
                    )
                )
                .all()
            )
            logger.info(f"Found {len(themes)} custom themes in database")
        except Exception as db_error:
            logger.error(f"Database error querying themes: {db_error}")
            themes = []

        # All themes are now stored in database - no more hardcoded built-in themes
        logger.info(f"Loading all themes from database")

        # Convert to response format
        all_themes = []

        # Add all themes from database
        for theme in themes:
            theme_data = {
                "id": str(theme.id),
                "name": theme.name,
                "display_name": theme.display_name or theme.name,
                "description": theme.description,
                "is_built_in": theme.is_built_in or False,
                "is_public": theme.is_public or False,
                "theme_data": theme.theme_data,
                "light_theme_data": theme.light_theme_data,
                "created_by": theme.created_by,
                "created_at": theme.created_at,
                "updated_at": theme.updated_at,
            }
            all_themes.append(theme_data)

        logger.info(f"Returning {len(all_themes)} total themes")
        return {"themes": all_themes}

    except Exception as e:
        logger.error(f"Error loading themes: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/current")
async def get_current_theme(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get current active theme with proper theme data"""
    try:
        # Get current theme setting from database
        from src.database.models import Setting

        theme_setting = session.query(Setting).filter(Setting.key == "ui_theme").first()
        current_theme_name = theme_setting.value if theme_setting else "default"

        logger.info(f"Current theme from settings: {current_theme_name}")

        # Look for theme in database (all themes are now in database)
        theme = (
            session.query(CustomTheme)
            .filter(CustomTheme.name == current_theme_name)
            .first()
        )

        if theme:
            # Return theme from database
            current_theme = {
                "id": str(theme.id),
                "name": theme.name,
                "display_name": theme.display_name or theme.name.title(),
                "description": theme.description or f"{theme.name} theme",
                "is_built_in": theme.is_built_in,
                "is_public": theme.is_public,
                "theme_data": theme.theme_data,
                "light_theme_data": theme.light_theme_data,
                "is_active": True,
            }
            logger.info(f"Returning theme from database: {current_theme['name']}")
            return current_theme

        # Fallback to default theme from database
        logger.warning(
            f"Theme '{current_theme_name}' not found, falling back to default"
        )
        default_theme = (
            session.query(CustomTheme).filter(CustomTheme.name == "default").first()
        )

        if default_theme:
            current_theme = {
                "id": str(default_theme.id),
                "name": default_theme.name,
                "display_name": default_theme.display_name,
                "description": default_theme.description,
                "is_built_in": default_theme.is_built_in,
                "is_public": default_theme.is_public,
                "theme_data": default_theme.theme_data,
                "light_theme_data": default_theme.light_theme_data,
                "is_active": True,
            }
        else:
            # Final fallback if default theme not in database
            current_theme = {
                "id": "default",
                "name": "default",
                "display_name": "Default",
                "description": "Default MVidarr theme",
                "is_built_in": True,
                "is_public": True,
                "theme_data": None,
                "light_theme_data": None,
                "is_active": True,
            }

        return current_theme

    except Exception as e:
        logger.error(f"Error getting current theme: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/apply")
async def apply_theme(
    request: ApplyThemeRequest,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Apply a theme"""
    try:
        theme_identifier = request.theme_name
        user_id = current_user.get("user_id", 6)

        logger.info(f"Applying theme '{theme_identifier}' for user {user_id}")

        # Check if theme exists in database (by name OR by ID)
        theme = None

        # First try to find by name
        theme = (
            session.query(CustomTheme)
            .filter(
                CustomTheme.name == theme_identifier,
                or_(
                    CustomTheme.is_public == True,
                    CustomTheme.created_by == user_id,
                ),
            )
            .first()
        )

        # If not found by name, try by ID (in case frontend sends ID instead of name)
        if not theme and theme_identifier.isdigit():
            theme_id = int(theme_identifier)
            theme = (
                session.query(CustomTheme)
                .filter(
                    CustomTheme.id == theme_id,
                    or_(
                        CustomTheme.is_public == True,
                        CustomTheme.created_by == user_id,
                    ),
                )
                .first()
            )

        if not theme:
            logger.error(f"Theme '{theme_identifier}' not found for user {user_id}")
            raise HTTPException(status_code=404, detail="Theme not found")

        # Save the theme preference to settings
        from src.database.models import Setting

        # Update or create ui_theme setting (always save the theme name, not ID)
        theme_setting = session.query(Setting).filter(Setting.key == "ui_theme").first()
        if theme_setting:
            theme_setting.value = theme.name
        else:
            theme_setting = Setting(
                key="ui_theme", value=theme.name, description="Current UI theme"
            )
            session.add(theme_setting)

        session.commit()
        logger.info(f"Theme preference saved: {theme.name}")

        return {
            "success": True,
            "message": f"Theme '{theme.name}' applied successfully",
            "theme_name": theme.name,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error applying theme: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/built-in/{theme_name}/extract")
async def extract_built_in_theme(
    theme_name: str = FastAPIPath(...),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Extract theme data from database"""
    try:
        # Get theme from database
        theme = (
            session.query(CustomTheme)
            .filter(CustomTheme.name == theme_name, CustomTheme.is_built_in == True)
            .first()
        )

        if not theme:
            # Return default theme data structure for unknown themes
            theme_data = {
                "theme_name": theme_name,
                "display_name": theme_name.title(),
                "description": f"Built-in {theme_name} theme",
                "variables": {},
            }
        else:
            theme_data = {
                "theme_name": theme.name,
                "display_name": theme.display_name,
                "description": theme.description,
                "variables": theme.theme_data or {},
            }

        logger.info(f"Extracted theme data for: {theme_name}")
        return theme_data

    except Exception as e:
        logger.error(f"Error extracting theme data: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("", response_model=Dict[str, Any])
async def create_theme(
    theme_data: ThemeData,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Create a new custom theme"""
    try:
        user_id = current_user.get("user_id", 6)

        # Check if theme name already exists
        existing = (
            session.query(CustomTheme)
            .filter(CustomTheme.name == theme_data.name)
            .first()
        )

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Theme with name '{theme_data.name}' already exists",
            )

        # Create new theme
        new_theme = CustomTheme(
            name=theme_data.name,
            display_name=theme_data.display_name,
            description=theme_data.description,
            theme_data=theme_data.theme_data,
            light_theme_data=theme_data.light_theme_data,
            is_public=theme_data.is_public,
            is_built_in=False,
            created_by=user_id,
            created_at=datetime.utcnow(),
        )

        session.add(new_theme)
        session.commit()
        session.refresh(new_theme)

        logger.info(f"Created new theme: {theme_data.name}")

        return {
            "success": True,
            "message": f"Theme '{theme_data.name}' created successfully",
            "theme_id": new_theme.id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating theme: {e}")
        session.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{theme_id}")
async def get_theme(
    theme_id: int = FastAPIPath(..., ge=1),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get a specific theme by ID"""
    try:
        user_id = current_user.get("user_id", 6)

        theme = (
            session.query(CustomTheme)
            .filter(
                CustomTheme.id == theme_id,
                or_(
                    CustomTheme.is_public == True,
                    CustomTheme.created_by == user_id,
                ),
            )
            .first()
        )

        if not theme:
            raise HTTPException(status_code=404, detail="Theme not found")

        return {
            "id": theme.id,
            "name": theme.name,
            "display_name": theme.display_name,
            "description": theme.description,
            "theme_data": theme.theme_data,
            "light_theme_data": theme.light_theme_data,
            "is_built_in": theme.is_built_in,
            "is_public": theme.is_public,
            "created_by": theme.created_by,
            "created_at": theme.created_at,
            "updated_at": theme.updated_at,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting theme {theme_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{theme_id}")
async def delete_theme(
    theme_id: int = FastAPIPath(..., description="Theme ID to delete"),
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_authentication),
):
    """
    Delete a custom theme

    Only custom themes can be deleted, not built-in themes, and only by
    the theme's own creator.
    """
    try:
        user_id = current_user.get("user_id", 6)
        theme = db.query(CustomTheme).filter(CustomTheme.id == theme_id).first()

        if not theme:
            raise HTTPException(status_code=404, detail="Theme not found")

        # Prevent deletion of built-in themes
        if theme.is_built_in:
            raise HTTPException(status_code=403, detail="Cannot delete built-in themes")

        # Only the creator can delete their theme. A private theme
        # belonging to someone else 404s (matches get_theme()'s own
        # not-found-for-invisible-theme behavior, so this doesn't confirm
        # a private theme id even exists); a public one 403s, since its
        # existence is already visible via GET /api/themes.
        if theme.created_by != user_id:
            if theme.is_public:
                raise HTTPException(
                    status_code=403,
                    detail="You don't have permission to delete this theme",
                )
            raise HTTPException(status_code=404, detail="Theme not found")

        # Delete the theme
        db.delete(theme)
        db.commit()

        logger.info(f"Deleted theme: {theme.name} (ID: {theme_id})")

        return {
            "success": True,
            "message": f"Theme '{theme.display_name or theme.name}' deleted successfully",
            "theme_id": theme_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting theme {theme_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/export/all")
async def export_all_themes(
    db: Session = Depends(get_db_session),
    current_user: dict = Depends(require_authentication),
):
    """
    Export all custom themes as JSON

    Returns a JSON file containing the caller's own custom (non-built-in)
    themes plus any public ones, that can be imported into another
    instance.
    """
    try:
        user_id = current_user.get("user_id", 6)
        # Exclude built-in themes, and scope to the caller's own themes
        # plus public ones -- matches get_themes()'s existing visibility
        # filter. Without this, any authenticated user could export
        # every other user's private theme data.
        themes = (
            db.query(CustomTheme)
            .filter(
                CustomTheme.is_built_in == False,
                or_(
                    CustomTheme.created_by == user_id,
                    CustomTheme.is_public == True,
                ),
            )
            .all()
        )

        # Build export data structure (even if empty)
        export_data = {
            "export_version": "1.0",
            "export_date": datetime.utcnow().isoformat(),
            "theme_count": len(themes),
            "themes": [
                {
                    "name": theme.name,
                    "display_name": theme.display_name,
                    "description": theme.description,
                    "theme_data": theme.theme_data,
                    "light_theme_data": theme.light_theme_data,
                    "is_public": theme.is_public,
                }
                for theme in themes
            ],
        }

        # Convert to JSON
        json_content = json.dumps(export_data, indent=2)

        logger.info(f"Exported {len(themes)} custom themes")

        # Return as downloadable JSON file
        return Response(
            content=json_content,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=mvidarr_themes_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting themes: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
