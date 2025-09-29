"""
FastAPI Security Router
Migrated from Flask src/api/security.py - Certificate management endpoints
"""

import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.fastapi.auth_dependencies import require_authentication_legacy
from src.database.connection import get_db_session
from src.utils.logger import get_logger

logger = logging.getLogger("mvidarr.fastapi.security")

router = APIRouter(
    prefix="/api/security",
    tags=["security"],
    responses={
        404: {"description": "Not found"},
        422: {"description": "Validation error"},
    },
)

# Certificate storage paths
CERT_DIR = Path("data/certificates")
CERT_DIR.mkdir(parents=True, exist_ok=True)

CERT_FILE = CERT_DIR / "certificate.crt"
KEY_FILE = CERT_DIR / "private.key"
CHAIN_FILE = CERT_DIR / "chain.crt"

# ========================================================================================
# PYDANTIC MODELS FOR REQUEST/RESPONSE VALIDATION
# ========================================================================================


class CertificateInfo(BaseModel):
    """Certificate information model"""

    subject: str
    issuer: str
    not_before: str
    not_after: str
    serial_number: str
    version: str
    signature_algorithm: str
    alt_names: List[str] = Field(default_factory=list)
    days_until_expiry: int
    is_currently_valid: bool


class CertificateStatus(BaseModel):
    """Certificate status model"""

    certificate_exists: bool
    private_key_exists: bool
    certificate_chain_exists: bool
    expiry_date: Optional[str] = None
    days_until_expiry: Optional[int] = None
    is_valid: bool = False
    subject: Optional[str] = None
    issuer: Optional[str] = None


class CertificateValidation(BaseModel):
    """Certificate validation result"""

    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: Optional[List[str]] = None
    subject: Optional[str] = None
    issuer: Optional[str] = None
    not_before: Optional[str] = None
    not_after: Optional[str] = None
    days_until_expiry: Optional[int] = None
    is_currently_valid: Optional[bool] = None


class CertificateUploadResponse(BaseModel):
    """Certificate upload response"""

    success: bool
    message: str
    certificate_info: Optional[Dict[str, Any]] = None


class CertificateRemovalResponse(BaseModel):
    """Certificate removal response"""

    success: bool
    message: str
    removed_files: List[str]


# ========================================================================================
# CERTIFICATE VALIDATION HELPER FUNCTIONS
# ========================================================================================


def validate_certificate_file(file_content: bytes) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Validate a certificate file and extract information

    Returns:
        tuple: (is_valid, error_message, cert_info)
    """
    try:
        cert = x509.load_pem_x509_certificate(file_content)

        # Extract certificate information
        cert_info = {
            "subject": cert.subject.rfc4514_string(),
            "issuer": cert.issuer.rfc4514_string(),
            "not_before": cert.not_valid_before.isoformat(),
            "not_after": cert.not_valid_after.isoformat(),
            "serial_number": str(cert.serial_number),
            "version": cert.version.name,
            "signature_algorithm": cert.signature_algorithm_oid._name,
        }

        # Check for Subject Alternative Names
        try:
            san_ext = cert.extensions.get_extension_for_oid(
                x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
            )
            alt_names = [name.value for name in san_ext.value]
            cert_info["alt_names"] = alt_names
        except x509.ExtensionNotFound:
            cert_info["alt_names"] = []

        # Calculate days until expiry
        now = datetime.utcnow()
        days_until_expiry = (cert.not_valid_after - now).days
        cert_info["days_until_expiry"] = days_until_expiry

        # Check if certificate is currently valid
        is_valid = cert.not_valid_before <= now <= cert.not_valid_after
        cert_info["is_currently_valid"] = is_valid

        return True, "", cert_info

    except Exception as e:
        return False, f"Invalid certificate format: {str(e)}", {}


def validate_private_key_file(file_content: bytes) -> Tuple[bool, str]:
    """
    Validate a private key file

    Returns:
        tuple: (is_valid, error_message)
    """
    try:
        # Try to load as PEM format
        try:
            serialization.load_pem_private_key(file_content, password=None)
            return True, ""
        except TypeError:
            # Might be password protected
            return False, "Private key appears to be password protected (not supported)"
        except ValueError:
            # Try different formats or provide error
            return False, "Invalid private key format or unsupported key type"

    except Exception as e:
        return False, f"Error validating private key: {str(e)}"


# ========================================================================================
# CERTIFICATE STATUS AND INFORMATION ENDPOINTS
# ========================================================================================


@router.get("/certificates/status", response_model=Dict[str, Any])
async def get_certificate_status(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Get current certificate status"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(
            f"Getting certificate status for user {current_user.get('username')}"
        )

        status = CertificateStatus(
            certificate_exists=CERT_FILE.exists(),
            private_key_exists=KEY_FILE.exists(),
            certificate_chain_exists=CHAIN_FILE.exists(),
            is_valid=False,
        )

        # If certificate exists, get additional info
        if status.certificate_exists:
            try:
                with open(CERT_FILE, "rb") as f:
                    cert_content = f.read()

                is_valid, error, cert_info = validate_certificate_file(cert_content)
                if is_valid:
                    status.expiry_date = cert_info["not_after"]
                    status.days_until_expiry = cert_info["days_until_expiry"]
                    status.is_valid = cert_info["is_currently_valid"]
                    status.subject = cert_info["subject"]
                    status.issuer = cert_info["issuer"]

            except Exception as e:
                logger.warning(f"Error reading certificate file: {e}")

        return {"success": True, "status": status.dict()}

    except Exception as e:
        logger.error(f"Error getting certificate status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/certificates/validate", response_model=Dict[str, Any])
async def validate_certificate(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Validate the current certificate"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Validating certificate for user {current_user.get('username')}")

        if not CERT_FILE.exists():
            raise HTTPException(status_code=404, detail="No certificate file found")

        # Read and validate certificate
        with open(CERT_FILE, "rb") as f:
            cert_content = f.read()

        is_valid, error, cert_info = validate_certificate_file(cert_content)

        validation_result = CertificateValidation(
            valid=is_valid,
            errors=[error] if error else [],
            **cert_info if is_valid else {},
        )

        # Additional validation checks
        if is_valid:
            warnings = []

            # Check if certificate is expiring soon (within 30 days)
            if cert_info["days_until_expiry"] < 30:
                warnings.append(
                    f"Certificate expires in {cert_info['days_until_expiry']} days"
                )

            if warnings:
                validation_result.warnings = warnings

            # Check if private key exists and matches
            if KEY_FILE.exists():
                try:
                    with open(KEY_FILE, "rb") as f:
                        key_content = f.read()
                    key_valid, key_error = validate_private_key_file(key_content)
                    if not key_valid:
                        validation_result.errors.append(
                            f"Private key issue: {key_error}"
                        )
                        validation_result.valid = False
                except Exception as e:
                    validation_result.errors.append(
                        f"Error reading private key: {str(e)}"
                    )
                    validation_result.valid = False
            else:
                validation_result.errors.append("Private key file not found")
                validation_result.valid = False

        return {"success": True, "validation": validation_result.dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating certificate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================================================================================
# CERTIFICATE UPLOAD AND MANAGEMENT ENDPOINTS
# ========================================================================================


@router.post("/certificates/upload", response_model=CertificateUploadResponse)
async def upload_certificates(
    certificate: UploadFile = File(..., description="Certificate file (.crt or .pem)"),
    private_key: UploadFile = File(..., description="Private key file (.key or .pem)"),
    certificate_chain: Optional[UploadFile] = File(
        None, description="Certificate chain file (optional)"
    ),
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Upload new SSL certificates"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Uploading certificates for user {current_user.get('username')}")

        # Validate required files
        if not certificate.filename or not private_key.filename:
            raise HTTPException(status_code=400, detail="No files selected")

        # Read and validate certificate
        cert_content = await certificate.read()
        is_valid, error, cert_info = validate_certificate_file(cert_content)
        if not is_valid:
            raise HTTPException(
                status_code=400, detail=f"Certificate validation failed: {error}"
            )

        # Read and validate private key
        key_content = await private_key.read()
        is_valid, error = validate_private_key_file(key_content)
        if not is_valid:
            raise HTTPException(
                status_code=400, detail=f"Private key validation failed: {error}"
            )

        # Backup existing files if they exist
        backup_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        if CERT_FILE.exists():
            shutil.copy2(
                CERT_FILE, CERT_DIR / f"certificate_backup_{backup_suffix}.crt"
            )
        if KEY_FILE.exists():
            shutil.copy2(KEY_FILE, CERT_DIR / f"private_backup_{backup_suffix}.key")

        # Save new certificate and key
        with open(CERT_FILE, "wb") as f:
            f.write(cert_content)
        with open(KEY_FILE, "wb") as f:
            f.write(key_content)

        # Set secure permissions
        os.chmod(CERT_FILE, 0o644)
        os.chmod(KEY_FILE, 0o600)  # Private key should be more restricted

        # Handle optional certificate chain
        if certificate_chain and certificate_chain.filename:
            chain_content = await certificate_chain.read()
            with open(CHAIN_FILE, "wb") as f:
                f.write(chain_content)
            os.chmod(CHAIN_FILE, 0o644)

        logger.info(
            f"SSL certificates uploaded successfully - expires: {cert_info['not_after']}"
        )

        return CertificateUploadResponse(
            success=True,
            message="Certificates uploaded successfully",
            certificate_info={
                "subject": cert_info["subject"],
                "expiry_date": cert_info["not_after"],
                "days_until_expiry": cert_info["days_until_expiry"],
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading certificates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/certificates/download")
async def download_certificate(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Download the current certificate file"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Downloading certificate for user {current_user.get('username')}")

        if not CERT_FILE.exists():
            raise HTTPException(status_code=404, detail="No certificate file found")

        return FileResponse(
            path=str(CERT_FILE),
            filename="mvidarr-certificate.crt",
            media_type="application/x-x509-ca-cert",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading certificate: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/certificates/remove", response_model=CertificateRemovalResponse)
async def remove_certificates(
    current_user: dict = Depends(require_authentication_legacy),
    session: Session = Depends(get_db_session),
):
    """Remove SSL certificates"""
    try:
        user_id = current_user.get("user_id", 1)

        logger.info(f"Removing certificates for user {current_user.get('username')}")

        removed_files = []

        # Backup files before removal
        backup_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")

        if CERT_FILE.exists():
            backup_path = CERT_DIR / f"certificate_removed_{backup_suffix}.crt"
            shutil.move(str(CERT_FILE), str(backup_path))
            removed_files.append("certificate")

        if KEY_FILE.exists():
            backup_path = CERT_DIR / f"private_removed_{backup_suffix}.key"
            shutil.move(str(KEY_FILE), str(backup_path))
            removed_files.append("private_key")

        if CHAIN_FILE.exists():
            backup_path = CERT_DIR / f"chain_removed_{backup_suffix}.crt"
            shutil.move(str(CHAIN_FILE), str(backup_path))
            removed_files.append("certificate_chain")

        if not removed_files:
            raise HTTPException(
                status_code=404, detail="No certificate files found to remove"
            )

        logger.info(f"SSL certificates removed: {', '.join(removed_files)}")

        return CertificateRemovalResponse(
            success=True,
            message=f"Removed {', '.join(removed_files)} (backed up with timestamp)",
            removed_files=removed_files,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing certificates: {e}")
        raise HTTPException(status_code=500, detail=str(e))
