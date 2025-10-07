#!/usr/bin/env python3
"""
Production Setup and Configuration Validator for MVidarr
Validates environment, creates necessary directories, and checks production readiness
"""

import os
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config.production_config import (
    ProductionSettings,
    Environment,
    create_sample_env_file,
    load_production_config
)
from src.utils.structured_logger import setup_structured_logging, get_structured_logger


def setup_directories(config: ProductionSettings) -> bool:
    """Create necessary directories for production deployment"""
    logger = get_structured_logger("mvidarr.setup")
    
    directories = [
        config.storage.video_directory,
        config.storage.thumbnail_directory,
        Path("logs"),
        Path("data"),
        Path("temp")
    ]
    
    if config.storage.backup_directory:
        directories.append(config.storage.backup_directory)
    
    success = True
    for directory in directories:
        try:
            directory.mkdir(parents=True, exist_ok=True)
            logger.info(f"Directory created/verified: {directory}")
            
            # Set appropriate permissions for production
            if config.environment == Environment.PRODUCTION:
                os.chmod(directory, 0o755)
                
        except Exception as e:
            logger.error(f"Failed to create directory {directory}: {e}")
            success = False
    
    return success


def validate_database_connection(config: ProductionSettings) -> bool:
    """Validate database connection and configuration"""
    logger = get_structured_logger("mvidarr.setup")
    
    try:
        # Test database connection
        from src.database.connection import DatabaseManager
        
        db_manager = DatabaseManager(config)
        
        # Test connection
        if not db_manager.test_connection():
            logger.error("Database connection test failed")
            return False
        
        logger.info("Database connection test passed")
        
        # Check if database exists, create if needed
        if not db_manager.create_database_if_not_exists():
            logger.error("Failed to create/verify database")
            return False
        
        logger.info("Database exists and is accessible")
        return True
        
    except Exception as e:
        logger.error(f"Database validation failed: {e}")
        return False


def validate_redis_connection(config: ProductionSettings) -> bool:
    """Validate Redis connection if configured"""
    logger = get_structured_logger("mvidarr.setup")
    
    if not config.redis:
        logger.info("Redis not configured, skipping validation")
        return True
    
    try:
        import redis
        
        if config.redis.url:
            r = redis.from_url(
                config.redis.url,
                socket_timeout=config.redis.socket_timeout,
                socket_connect_timeout=config.redis.socket_connect_timeout
            )
        else:
            r = redis.Redis(
                host=config.redis.host,
                port=config.redis.port,
                password=config.redis.password,
                db=config.redis.db,
                ssl=config.redis.ssl,
                socket_timeout=config.redis.socket_timeout,
                socket_connect_timeout=config.redis.socket_connect_timeout
            )
        
        # Test connection
        r.ping()
        logger.info("Redis connection test passed")
        return True
        
    except Exception as e:
        logger.error(f"Redis connection test failed: {e}")
        return False


def validate_storage_permissions(config: ProductionSettings) -> bool:
    """Validate storage directory permissions"""
    logger = get_structured_logger("mvidarr.setup")
    
    directories = [
        config.storage.video_directory,
        config.storage.thumbnail_directory
    ]
    
    if config.storage.backup_directory:
        directories.append(config.storage.backup_directory)
    
    success = True
    for directory in directories:
        try:
            # Test write permissions
            test_file = directory / ".write_test"
            test_file.write_text("test")
            test_file.unlink()
            
            logger.info(f"Write permissions verified for: {directory}")
            
        except Exception as e:
            logger.error(f"Write permission test failed for {directory}: {e}")
            success = False
    
    return success


def validate_security_settings(config: ProductionSettings) -> bool:
    """Validate security configuration"""
    logger = get_structured_logger("mvidarr.setup")
    
    issues = []
    
    # Check secret key strength
    if len(config.security.secret_key) < 32:
        issues.append("Secret key is too short (minimum 32 characters)")
    
    # Check production-specific security settings
    if config.environment == Environment.PRODUCTION:
        if not config.security.secure_cookies:
            issues.append("Secure cookies must be enabled in production")
        
        if config.debug:
            issues.append("Debug mode must be disabled in production")
        
        if config.security.secret_key == "change-me-in-production":
            issues.append("Default secret key detected in production")
    
    if issues:
        for issue in issues:
            logger.error(f"Security issue: {issue}")
        return False
    
    logger.info("Security configuration validated successfully")
    return True


def check_system_requirements() -> bool:
    """Check system requirements for production deployment"""
    logger = get_structured_logger("mvidarr.setup")
    
    requirements = []
    
    # Check Python version
    python_version = sys.version_info
    if python_version < (3, 9):
        requirements.append(f"Python 3.9+ required, found {python_version.major}.{python_version.minor}")
    
    # Check available memory
    try:
        import psutil
        memory = psutil.virtual_memory()
        memory_gb = memory.total / (1024**3)
        
        if memory_gb < 2:
            requirements.append(f"Minimum 2GB RAM recommended, found {memory_gb:.1f}GB")
        
        logger.info(f"System memory: {memory_gb:.1f}GB")
        
    except ImportError:
        logger.warning("psutil not available, skipping memory check")
    
    # Check disk space
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        free_gb = free / (1024**3)
        
        if free_gb < 10:
            requirements.append(f"Minimum 10GB free disk space recommended, found {free_gb:.1f}GB")
        
        logger.info(f"Free disk space: {free_gb:.1f}GB")
        
    except Exception as e:
        logger.warning(f"Disk space check failed: {e}")
    
    if requirements:
        for req in requirements:
            logger.warning(f"System requirement: {req}")
        return False
    
    logger.info("System requirements check passed")
    return True


def main():
    """Main setup and validation function"""
    print("🚀 MVidarr Production Setup and Validation")
    print("=" * 50)
    
    # Setup structured logging
    setup_structured_logging()
    logger = get_structured_logger("mvidarr.setup")
    
    # Load configuration
    try:
        config = load_production_config()
        logger.info(f"Configuration loaded for environment: {config.environment}")
        
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        print("\n❌ Configuration loading failed")
        
        # Create sample env file
        create_sample_env_file()
        print("📝 Sample .env.example file created")
        print("Please copy .env.example to .env and customize your configuration")
        return False
    
    print(f"\n📋 Environment: {config.environment.value}")
    print(f"📋 Application: {config.app_name} v{config.app_version}")
    print(f"📋 Host: {config.app_host}:{config.app_port}")
    
    # Validation steps
    validation_steps = [
        ("System Requirements", check_system_requirements),
        ("Security Settings", lambda: validate_security_settings(config)),
        ("Directory Setup", lambda: setup_directories(config)),
        ("Storage Permissions", lambda: validate_storage_permissions(config)),
        ("Database Connection", lambda: validate_database_connection(config)),
        ("Redis Connection", lambda: validate_redis_connection(config)),
    ]
    
    print("\n🔍 Running validation checks...")
    
    all_passed = True
    for step_name, step_func in validation_steps:
        try:
            print(f"\n  Checking {step_name}...", end=" ")
            
            if step_func():
                print("✅ PASSED")
            else:
                print("❌ FAILED")
                all_passed = False
                
        except Exception as e:
            print(f"❌ ERROR: {e}")
            logger.error(f"{step_name} validation error: {e}")
            all_passed = False
    
    # Production readiness check
    if config.environment == Environment.PRODUCTION:
        print("\n🔒 Production readiness check...")
        
        production_issues = config.validate_production_readiness()
        if production_issues:
            print("❌ Production readiness issues found:")
            for issue in production_issues:
                print(f"   - {issue}")
            all_passed = False
        else:
            print("✅ Production readiness validated")
    
    # Summary
    print("\n" + "=" * 50)
    
    if all_passed:
        print("✅ All validation checks passed!")
        print("🚀 MVidarr is ready for deployment")
        
        if config.environment == Environment.PRODUCTION:
            print("\n📋 Production deployment checklist:")
            print("   - Database is accessible and configured")
            print("   - Storage directories are created with proper permissions")
            print("   - Security settings are production-ready")
            print("   - System requirements are met")
            print("   - Redis is configured (if enabled)")
            
            print("\n🔧 Next steps:")
            print("   1. Start the application: uvicorn fastapi_app:app --host 0.0.0.0 --port 5000")
            print("   2. Check health status: curl http://localhost:5000/api/health/production")
            print("   3. Monitor logs: tail -f logs/mvidarr_structured.log")
        
        return True
        
    else:
        print("❌ Validation failed - please address the issues above")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)