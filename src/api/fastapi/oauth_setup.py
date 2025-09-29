"""
OAuth2 Setup API Endpoints
Provides interface for users to configure YouTube OAuth2 authentication
"""

import asyncio
import json
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.services.youtube_download_engine import youtube_download_engine
from src.services.youtube_oauth_service import youtube_oauth_service
from src.utils.logger import get_logger

logger = get_logger("mvidarr.oauth_setup_api")

router = APIRouter()


class OAuthCredentials(BaseModel):
    client_id: str
    client_secret: str


class OAuthSetupResponse(BaseModel):
    success: bool
    message: str
    setup_url: Optional[str] = None


@router.post("/setup-credentials", response_model=OAuthSetupResponse)
async def setup_oauth_credentials(credentials: OAuthCredentials):
    """
    Set up OAuth2 credentials from Google Console
    User must provide client_id and client_secret from their Google API project
    """
    try:
        success = youtube_oauth_service.setup_oauth_credentials(
            credentials.client_id, credentials.client_secret
        )

        if success:
            return OAuthSetupResponse(
                success=True, message="OAuth2 credentials configured successfully"
            )
        else:
            return OAuthSetupResponse(
                success=False, message="Failed to configure OAuth2 credentials"
            )

    except Exception as e:
        logger.error(f"OAuth credentials setup failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to setup credentials: {str(e)}",
        )


@router.post("/start-authorization", response_model=OAuthSetupResponse)
async def start_oauth_authorization():
    """
    Start OAuth2 authorization flow
    Returns URL for user to visit for authorization
    """
    try:
        auth_url = youtube_oauth_service.start_oauth_flow()

        return OAuthSetupResponse(
            success=True,
            message="Authorization flow started. Please visit the provided URL to authorize MVidarr.",
            setup_url=auth_url,
        )

    except ValueError as e:
        return OAuthSetupResponse(success=False, message=str(e))
    except Exception as e:
        logger.error(f"OAuth authorization start failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start authorization: {str(e)}",
        )


@router.post("/complete-authorization", response_model=OAuthSetupResponse)
async def complete_oauth_authorization(timeout: int = 300):
    """
    Complete OAuth2 authorization flow
    Waits for user to complete authorization and exchanges code for tokens
    """
    try:
        # Use asyncio to avoid blocking the API
        success = await asyncio.get_event_loop().run_in_executor(
            None, youtube_oauth_service.complete_oauth_flow, timeout
        )

        if success:
            return OAuthSetupResponse(
                success=True,
                message="OAuth2 authorization completed successfully! YouTube downloads will now use authenticated API access.",
            )
        else:
            return OAuthSetupResponse(
                success=False,
                message="Authorization timed out or failed. Please try again.",
            )

    except Exception as e:
        logger.error(f"OAuth authorization completion failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to complete authorization: {str(e)}",
        )


@router.get("/status")
async def get_oauth_status():
    """
    Get current OAuth2 authentication status
    """
    try:
        is_configured = youtube_oauth_service.client_id is not None
        is_authenticated = youtube_oauth_service.is_authenticated()

        return {
            "credentials_configured": is_configured,
            "authenticated": is_authenticated,
            "message": (
                "OAuth2 fully configured and authenticated"
                if is_authenticated
                else (
                    "OAuth2 credentials configured, but not authenticated"
                    if is_configured
                    else "OAuth2 not configured"
                )
            ),
        }

    except Exception as e:
        logger.error(f"OAuth status check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check status: {str(e)}",
        )


@router.post("/test-download-capability")
async def test_download_capability():
    """
    Test download capabilities with all strategies
    Returns which download methods are working
    """
    try:
        # Use asyncio to avoid blocking
        results = await asyncio.get_event_loop().run_in_executor(
            None, youtube_download_engine.test_download_capability
        )

        working_strategies = [
            strategy
            for strategy, result in results.items()
            if result.get("success", False)
        ]

        return {
            "success": len(working_strategies) > 0,
            "working_strategies": working_strategies,
            "test_results": results,
            "message": (
                f"{len(working_strategies)} of 5 download strategies are working"
                if working_strategies
                else "No download strategies are currently working"
            ),
        }

    except Exception as e:
        logger.error(f"Download capability test failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Test failed: {str(e)}",
        )


@router.get("/setup-instructions")
async def get_setup_instructions():
    """
    Get detailed instructions for setting up OAuth2
    """
    instructions = {
        "title": "YouTube OAuth2 Setup Instructions",
        "steps": [
            {
                "step": 1,
                "title": "Create Google Cloud Project",
                "description": "Go to https://console.cloud.google.com/ and create a new project or select existing one",
            },
            {
                "step": 2,
                "title": "Enable YouTube Data API v3",
                "description": "In the Google Cloud Console, go to 'APIs & Services' > 'Library' and enable 'YouTube Data API v3'",
            },
            {
                "step": 3,
                "title": "Create OAuth2 Credentials",
                "description": "Go to 'APIs & Services' > 'Credentials' and create 'OAuth 2.0 Client IDs' for a 'Web application'",
            },
            {
                "step": 4,
                "title": "Configure Redirect URI",
                "description": "Add 'http://localhost:8080/oauth/callback' to the authorized redirect URIs",
            },
            {
                "step": 5,
                "title": "Get Client Credentials",
                "description": "Download the client ID and client secret from your OAuth2 credentials",
            },
            {
                "step": 6,
                "title": "Configure MVidarr",
                "description": "Use the /setup-credentials endpoint to provide client_id and client_secret to MVidarr",
            },
            {
                "step": 7,
                "title": "Authorize Access",
                "description": "Use /start-authorization to begin OAuth flow, then /complete-authorization to finish",
            },
        ],
        "redirect_uri": "http://localhost:8080/oauth/callback",
        "required_scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
    }

    return instructions
