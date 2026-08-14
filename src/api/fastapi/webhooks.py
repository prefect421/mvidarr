"""
FastAPI Webhook Management Router
Migrated from Flask src/api/webhooks.py - Event-driven notification webhooks
"""

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field, HttpUrl, validator
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import require_authentication
from src.database.connection import get_db_session
from src.services.webhook_service import (
    WebhookEndpoint,
    WebhookEventType,
    webhook_service,
)

logger = logging.getLogger("mvidarr.fastapi.webhooks")

router = APIRouter(
    prefix="/api/webhooks",
    tags=["webhooks"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class WebhookEndpointRequest(BaseModel):
    """Webhook endpoint creation request"""

    # Declared FIRST, before url: pydantic's @validator only sees fields
    # in `values` that were declared (and already validated) earlier in
    # the class body. validate_url below reads values["provider_type"],
    # so provider_type must be declared above url or that lookup always
    # misses and silently falls back to the "generic" default.
    provider_type: str = Field(
        default="generic",
        pattern="^(generic|discord|apprise)$",
        description="Payload format/delivery mechanism for this endpoint",
    )
    # Plain str, not HttpUrl: Apprise endpoints use non-HTTP URL schemes
    # (e.g. "tgram://bottoken/ChatID", "discord://webhook_id/token") that
    # HttpUrl would reject outright. Real URL-shape validation for
    # generic/discord happens in validate_url below instead.
    url: str = Field(..., min_length=1, description="Webhook URL or Apprise URL string")
    secret: Optional[str] = Field(
        None, max_length=256, description="Secret for webhook verification"
    )
    events: List[str] = Field(
        default_factory=list, description="List of event types to subscribe to"
    )
    enabled: bool = Field(default=True, description="Whether webhook is enabled")
    max_retries: int = Field(
        default=3, ge=0, le=10, description="Maximum retry attempts"
    )
    timeout: int = Field(
        default=30, ge=1, le=300, description="Request timeout in seconds"
    )
    headers: Dict[str, str] = Field(
        default_factory=dict, description="Custom headers to include"
    )

    @validator("events")
    def validate_events(cls, v):
        """Validate event types against enum"""
        for event_str in v:
            try:
                WebhookEventType(event_str)
            except ValueError:
                raise ValueError(f"Invalid event type: {event_str}")
        return v

    @validator("url")
    def validate_url(cls, v, values):
        """Apprise URLs are not standard HTTP(S) URLs -- only require
        real URL shape for generic/discord, which are always plain HTTP(S)
        webhook endpoints."""
        provider_type = values.get("provider_type", "generic")
        if provider_type != "apprise":
            parsed = urlparse(v)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError(
                    "url must be a valid http(s) URL for generic/discord endpoints"
                )
        return v


class WebhookEndpointUpdate(BaseModel):
    """Webhook endpoint update request"""

    secret: Optional[str] = Field(None, max_length=256)
    events: Optional[List[str]] = None
    enabled: Optional[bool] = None
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    timeout: Optional[int] = Field(None, ge=1, le=300)
    headers: Optional[Dict[str, str]] = None
    provider_type: Optional[str] = Field(None, pattern="^(generic|discord|apprise)$")

    @validator("events")
    def validate_events(cls, v):
        """Validate event types against enum"""
        if v is not None:
            for event_str in v:
                try:
                    WebhookEventType(event_str)
                except ValueError:
                    raise ValueError(f"Invalid event type: {event_str}")
        return v


class WebhookTestRequest(BaseModel):
    """Webhook test request"""

    provider_type: str = Field(default="generic", pattern="^(generic|discord|apprise)$")
    url: str = Field(..., min_length=1, description="Webhook URL or Apprise URL string")
    secret: Optional[str] = Field(
        None, max_length=256, description="Secret for verification"
    )

    @validator("url")
    def validate_url(cls, v, values):
        provider_type = values.get("provider_type", "generic")
        if provider_type != "apprise":
            parsed = urlparse(v)
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError(
                    "url must be a valid http(s) URL for generic/discord endpoints"
                )
        return v


class WebhookTriggerRequest(BaseModel):
    """Webhook trigger request"""

    event_type: str = Field(..., description="Event type to trigger")
    data: Dict[str, Any] = Field(default_factory=dict, description="Event data payload")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Event metadata")

    @validator("event_type")
    def validate_event_type(cls, v):
        """Validate event type against enum"""
        try:
            WebhookEventType(v)
        except ValueError:
            raise ValueError(f"Invalid event type: {v}")
        return v


class WebhookValidationRequest(BaseModel):
    """Webhook validation request"""

    url: Optional[HttpUrl] = None
    secret: Optional[str] = Field(None, max_length=256)
    events: Optional[List[str]] = None
    enabled: Optional[bool] = None
    max_retries: Optional[int] = None
    timeout: Optional[int] = None
    headers: Optional[Dict[str, str]] = None


class WebhookEndpointResponse(BaseModel):
    """Webhook endpoint response"""

    url: str
    secret: Optional[str] = None
    events: List[str]
    enabled: bool
    max_retries: int
    timeout: int
    headers: Dict[str, str]
    created_at: Optional[str] = None
    last_triggered: Optional[str] = None


class WebhookStatsResponse(BaseModel):
    """Webhook statistics response"""

    total_endpoints: int
    enabled_endpoints: int
    disabled_endpoints: int
    event_types_used: List[str]
    endpoints_by_event: Dict[str, int]


# ========================================================================================
# WEBHOOK ENDPOINT MANAGEMENT
# ========================================================================================


@router.get("/")
async def get_webhooks(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get all webhook endpoints"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Getting webhooks for user {current_user.get('username')}")

        endpoints = webhook_service.get_endpoints()

        return {"webhooks": endpoints, "count": len(endpoints)}

    except Exception as e:
        logger.error(f"Failed to get webhooks: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/")
async def create_webhook(
    webhook_request: WebhookEndpointRequest,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Create a new webhook endpoint"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Creating webhook endpoint for URL '{webhook_request.url}' by user {current_user.get('username')}"
        )

        # Convert event strings to enum values
        events = []
        for event_str in webhook_request.events:
            events.append(WebhookEventType(event_str))

        endpoint = WebhookEndpoint(
            url=str(webhook_request.url),
            secret=webhook_request.secret,
            events=events,
            enabled=webhook_request.enabled,
            max_retries=webhook_request.max_retries,
            timeout=webhook_request.timeout,
            headers=webhook_request.headers,
            provider_type=webhook_request.provider_type,
        )

        success = webhook_service.add_endpoint(endpoint)

        if success:
            return {
                "success": True,
                "message": "Webhook endpoint created successfully",
                "url": str(webhook_request.url),
            }
        else:
            raise HTTPException(
                status_code=400, detail="Failed to create webhook endpoint"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.put("/{url:path}")
async def update_webhook(
    url: str = Path(..., description="Webhook URL to update"),
    update_request: WebhookEndpointUpdate = None,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Update webhook endpoint configuration"""
    try:
        user_id = current_user.get("user_id", 1)

        if update_request is None:
            raise HTTPException(status_code=400, detail="No data provided")

        logger.info(
            f"Updating webhook endpoint '{url}' for user {current_user.get('username')}"
        )

        # Convert to dict and filter out None values
        update_data = {k: v for k, v in update_request.dict().items() if v is not None}

        success = webhook_service.update_endpoint(url, update_data)

        if success:
            return {"success": True, "message": "Webhook endpoint updated successfully"}
        else:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{url:path}")
async def delete_webhook(
    url: str = Path(..., description="Webhook URL to delete"),
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Delete webhook endpoint"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Deleting webhook endpoint '{url}' for user {current_user.get('username')}"
        )

        success = webhook_service.remove_endpoint(url)

        if success:
            return {"success": True, "message": "Webhook endpoint deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

    except Exception as e:
        logger.error(f"Failed to delete webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# WEBHOOK TESTING AND VALIDATION
# ========================================================================================


@router.post("/test")
async def test_webhook(
    test_request: WebhookTestRequest,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Test webhook endpoint"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Testing webhook endpoint '{test_request.url}' for user {current_user.get('username')}"
        )

        result = webhook_service.test_endpoint(
            str(test_request.url),
            test_request.secret,
            provider_type=test_request.provider_type,
        )

        return {"test_result": result, "url": str(test_request.url)}

    except Exception as e:
        logger.error(f"Failed to test webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/validate")
async def validate_webhook(
    validation_request: WebhookValidationRequest,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Validate webhook configuration"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Validating webhook configuration for user {current_user.get('username')}"
        )

        validation_errors = []
        data = validation_request.dict()

        # Validate URL
        if "url" not in data or data["url"] is None:
            validation_errors.append("URL is required")
        elif not str(data["url"]).startswith(("http://", "https://")):
            validation_errors.append("URL must start with http:// or https://")

        # Validate event types
        if "events" in data and data["events"] is not None:
            for event_str in data["events"]:
                try:
                    WebhookEventType(event_str)
                except ValueError:
                    validation_errors.append(f"Invalid event type: {event_str}")

        # Validate max_retries
        if "max_retries" in data and data["max_retries"] is not None:
            max_retries = data["max_retries"]
            if max_retries < 0 or max_retries > 10:
                validation_errors.append("max_retries must be between 0 and 10")

        # Validate timeout
        if "timeout" in data and data["timeout"] is not None:
            timeout = data["timeout"]
            if timeout < 1 or timeout > 300:
                validation_errors.append("timeout must be between 1 and 300 seconds")

        # Validate headers
        if "headers" in data and data["headers"] is not None:
            if not isinstance(data["headers"], dict):
                validation_errors.append("headers must be a dictionary")

        if validation_errors:
            raise HTTPException(
                status_code=400, detail={"valid": False, "errors": validation_errors}
            )
        else:
            return {"valid": True, "message": "Webhook configuration is valid"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to validate webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ========================================================================================
# WEBHOOK EVENTS AND UTILITIES
# ========================================================================================


@router.get("/events")
async def get_event_types(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get available webhook event types"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting webhook event types for user {current_user.get('username')}"
        )

        event_types = webhook_service.get_event_types()

        return {"event_types": event_types, "count": len(event_types)}

    except Exception as e:
        logger.error(f"Failed to get event types: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/trigger")
async def trigger_webhook(
    trigger_request: WebhookTriggerRequest,
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Trigger a webhook event manually (for testing)"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Triggering webhook event '{trigger_request.event_type}' for user {current_user.get('username')}"
        )

        event_type = WebhookEventType(trigger_request.event_type)

        # Add test flag to metadata
        metadata = trigger_request.metadata.copy()
        metadata["test_trigger"] = True
        metadata["triggered_by"] = "api"
        metadata["user_id"] = user_id

        webhook_service.trigger_event(event_type, trigger_request.data, metadata)

        return {
            "success": True,
            "message": f"Webhook event {event_type.value} triggered successfully",
        }

    except Exception as e:
        logger.error(f"Failed to trigger webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats", response_model=WebhookStatsResponse)
async def get_webhook_stats(
    current_user: dict = Depends(require_authentication),
    session: Session = Depends(get_db_session),
):
    """Get webhook statistics"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting webhook statistics for user {current_user.get('username')}"
        )

        endpoints = webhook_service.get_endpoints()

        stats = {
            "total_endpoints": len(endpoints),
            "enabled_endpoints": len([ep for ep in endpoints if ep["enabled"]]),
            "disabled_endpoints": len([ep for ep in endpoints if not ep["enabled"]]),
            "event_types_used": set(),
            "endpoints_by_event": {},
        }

        for endpoint in endpoints:
            for event in endpoint["events"]:
                stats["event_types_used"].add(event)
                if event not in stats["endpoints_by_event"]:
                    stats["endpoints_by_event"][event] = 0
                stats["endpoints_by_event"][event] += 1

        stats["event_types_used"] = list(stats["event_types_used"])

        return WebhookStatsResponse(**stats)

    except Exception as e:
        logger.error(f"Failed to get webhook stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
