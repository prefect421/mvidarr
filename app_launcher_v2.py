#!/usr/bin/env python3
"""
MVidarr Smart Application Launcher v2
Supports both Flask and FastAPI applications with automatic migration detection
"""

import os
import sys
import sqlite3
import subprocess
import logging
import asyncio
import signal
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import threading

# Setup basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('mvidarr.launcher')

class MVidarrLauncherV2:
    """Smart launcher for MVidarr applications with Flask/FastAPI support"""
    
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.db_path = self.base_dir / 'data' / 'mvidarr.db'
        self.shutdown_event = threading.Event()
        
        # Application entry points
        self.app_configs = {
            'flask_simple_auth': {
                'file': 'src/app_with_simple_auth.py',
                'name': 'MVidarr Flask with Simple Authentication',
                'description': 'Flask-based single-user authentication',
                'framework': 'flask',
                'port': 5000
            },
            'flask_full_auth': {
                'file': 'app.py',
                'name': 'MVidarr Flask with Full Authentication',
                'description': 'Flask-based multi-user authentication with roles',
                'framework': 'flask',
                'port': 5000
            },
            'fastapi_hybrid': {
                'file': 'fastapi_app.py',
                'name': 'MVidarr FastAPI (Migration Mode)',
                'description': 'FastAPI with native async job system - Phase 1 migration',
                'framework': 'fastapi',
                'port': 5000,
                'concurrent_flask': True  # Run alongside Flask during migration
            },
            'fastapi_full': {
                'file': 'fastapi_app.py',
                'name': 'MVidarr FastAPI (Full Mode)',
                'description': 'Complete FastAPI application - Post migration',
                'framework': 'fastapi',
                'port': 5000,
                'concurrent_flask': False
            }
        }
    
    def get_migration_status(self):
        """Determine current migration status from roadmap and system state"""
        try:
            # Check for Phase 2 completion files first
            phase2_week19_complete = self.base_dir / 'PHASE_2_WEEK19_COMPLETION.md'
            phase2_week18_complete = self.base_dir / 'PHASE_2_WEEK18_COMPLETION.md'
            
            if phase2_week19_complete.exists():
                logger.info("Phase 2 Week 19 completion detected - Advanced FFmpeg operations available")
                return 'fastapi_hybrid'  # Phase 2 Week 19 complete
            elif phase2_week18_complete.exists():
                logger.info("Phase 2 Week 18 completion detected - FFmpeg streaming available")
                return 'fastapi_hybrid'  # Phase 2 Week 18 complete
            
            # Fallback to roadmap checking
            roadmap_path = self.base_dir / 'MILESTONE_ROADMAP.md'
            if roadmap_path.exists():
                content = roadmap_path.read_text()
                
                # Check migration phase status
                if '✅ **Phase 1**: Core FastAPI app structure and job API (COMPLETE)' in content:
                    if '✅ **Phase 2**: Critical API endpoints migration (COMPLETE)' in content:
                        if '✅ **Phase 3**: Web interface migration (COMPLETE)' in content:
                            return 'fastapi_full'  # Migration complete
                        else:
                            return 'fastapi_hybrid'  # Phase 2 complete, Phase 3 in progress
                    else:
                        return 'fastapi_hybrid'  # Phase 1 complete, Phase 2 in progress
                elif '🔄 **Phase 1**: Core FastAPI app structure and job API (IN PROGRESS)' in content:
                    return 'flask_simple_auth'  # Migration in progress, use Flask
                else:
                    return 'flask_simple_auth'  # No migration yet
            
            return 'flask_simple_auth'  # Default
            
        except Exception as e:
            logger.warning(f"Could not determine migration status: {e}")
            return 'flask_simple_auth'
    
    def get_auth_setting(self):
        """Get authentication setting from database"""
        try:
            if not self.db_path.exists():
                logger.warning(f"Database not found at {self.db_path}")
                return 'simple'  # Default to simple auth
            
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='settings'
            """)
            
            if not cursor.fetchone():
                logger.warning("Settings table not found in database")
                conn.close()
                return 'simple'
            
            cursor.execute("""
                SELECT value FROM settings 
                WHERE key = 'authentication_type'
            """)
            
            auth_type = cursor.fetchone()
            conn.close()
            
            if auth_type:
                auth_mode = auth_type[0].lower()
                if auth_mode in ['simple', 'single_user']:
                    return 'simple'
                elif auth_mode in ['full', 'multi_user', 'oauth']:
                    return 'full'
            
            return 'simple'
                
        except Exception as e:
            logger.error(f"Error reading database settings: {e}")
            return 'simple'
    
    def determine_application_mode(self):
        """Determine which application mode to use based on migration status and auth"""
        migration_status = self.get_migration_status()
        auth_setting = self.get_auth_setting()
        
        logger.info(f"Migration status: {migration_status}")
        logger.info(f"Auth setting: {auth_setting}")
        
        # During FastAPI migration phases
        if migration_status == 'fastapi_hybrid':
            return 'fastapi_hybrid'
        elif migration_status == 'fastapi_full':
            return 'fastapi_full'
        else:
            # Flask mode
            if auth_setting == 'simple':
                return 'flask_simple_auth'
            else:
                return 'flask_full_auth'
    
    def start_flask_app(self, config):
        """Start Flask application"""
        app_file = self.base_dir / config['file']
        
        logger.info(f"🌶️  Starting Flask app: {config['name']}")
        logger.info(f"📂 Entry point: {config['file']}")
        logger.info(f"🔗 URL: http://localhost:{config['port']}")
        
        # Use exec to replace the current process
        os.execv(sys.executable, [sys.executable, str(app_file)])
    
    def start_fastapi_app(self, config):
        """Start FastAPI application"""
        app_file = self.base_dir / config['file']
        
        logger.info(f"⚡ Starting FastAPI app: {config['name']}")
        logger.info(f"📂 Entry point: {config['file']}")
        logger.info(f"🔗 URL: http://localhost:{config['port']}")
        
        # Activate virtual environment and run FastAPI
        venv_python = self.base_dir / 'venv' / 'bin' / 'python'
        
        if venv_python.exists():
            logger.info("🐍 Using virtual environment")
            os.execv(str(venv_python), [str(venv_python), str(app_file)])
        else:
            logger.warning("⚠️  Virtual environment not found, using system Python")
            os.execv(sys.executable, [sys.executable, str(app_file)])
    
    def start_hybrid_mode(self, config):
        """Start FastAPI app with Phase 2 advanced processing"""
        app_file = self.base_dir / config['file']
        
        logger.info("🚀 Starting Phase 2 Advanced Processing mode")
        logger.info(f"⚡ FastAPI: {config['name']} on port {config['port']}")
        logger.info("🎯 Advanced FFmpeg Operations: ENABLED")
        logger.info("🐳 Docker configurations available for production deployment")
        logger.info("📖 See PHASE_2_WEEK19_COMPLETION.md for features")
        
        # For hybrid mode, we'll start FastAPI (Flask will be available separately)
        # In production, you might want to run both simultaneously using process managers
        
        venv_python = self.base_dir / 'venv' / 'bin' / 'python'
        
        if venv_python.exists():
            logger.info("🐍 Using virtual environment for FastAPI")
            os.execv(str(venv_python), [str(venv_python), str(app_file)])
        else:
            logger.warning("⚠️  Virtual environment not found, using system Python")
            os.execv(sys.executable, [sys.executable, str(app_file)])
    
    def check_dependencies(self, app_mode):
        """Check if required dependencies are installed"""
        config = self.app_configs[app_mode]
        
        if config['framework'] == 'fastapi':
            try:
                # Check if FastAPI dependencies are available
                venv_python = self.base_dir / 'venv' / 'bin' / 'python'
                
                if venv_python.exists():
                    result = subprocess.run([
                        str(venv_python), '-c', 
                        'import fastapi, uvicorn; print("FastAPI dependencies OK")'
                    ], capture_output=True, text=True, timeout=10)
                    
                    if result.returncode != 0:
                        logger.error("❌ FastAPI dependencies not installed")
                        logger.info("💡 Run: source venv/bin/activate && pip install -r requirements-fastapi.txt")
                        return False
                    else:
                        logger.info("✅ FastAPI dependencies available")
                        return True
                else:
                    logger.error("❌ Virtual environment not found")
                    logger.info("💡 Create virtual environment: python3 -m venv venv")
                    return False
                    
            except Exception as e:
                logger.error(f"❌ Error checking FastAPI dependencies: {e}")
                return False
        
        # For Flask, assume dependencies are available
        return True
    
    def launch_application(self, force_mode=None):
        """Launch the appropriate application"""
        
        # Determine application mode
        if force_mode and force_mode in self.app_configs:
            app_mode = force_mode
            logger.info(f"🎯 Forced mode: {app_mode}")
        else:
            app_mode = self.determine_application_mode()
            logger.info(f"🤖 Auto-detected mode: {app_mode}")
        
        config = self.app_configs[app_mode]
        
        # Check if application file exists
        app_file = self.base_dir / config['file']
        if not app_file.exists():
            logger.error(f"❌ Application file not found: {config['file']}")
            return False
        
        # Check dependencies
        if not self.check_dependencies(app_mode):
            return False
        
        # Change to application directory
        os.chdir(self.base_dir)
        
        # Show startup banner
        logger.info("=" * 70)
        logger.info("🎵 MVidarr Smart Launcher v2")
        logger.info("=" * 70)
        logger.info(f"🚀 Mode: {app_mode}")
        logger.info(f"📱 Application: {config['name']}")
        logger.info(f"📝 Description: {config['description']}")
        logger.info(f"🔧 Framework: {config['framework'].upper()}")
        logger.info("=" * 70)
        
        # Launch based on framework
        try:
            if config['framework'] == 'flask':
                self.start_flask_app(config)
            elif config['framework'] == 'fastapi':
                if app_mode == 'fastapi_hybrid':
                    self.start_hybrid_mode(config)
                else:
                    self.start_fastapi_app(config)
            
        except Exception as e:
            logger.error(f"❌ Failed to launch application: {e}")
            return False
        
        return True
    
    def show_status(self):
        """Show current configuration and available applications"""
        print("\n" + "=" * 70)
        print("🎵 MVidarr Launcher v2 Status")
        print("=" * 70)
        
        # Show migration status
        migration_status = self.get_migration_status()
        auth_setting = self.get_auth_setting()
        recommended_mode = self.determine_application_mode()
        
        print(f"📊 Migration Status: {migration_status}")
        print(f"🔐 Auth Setting: {auth_setting}")
        print(f"🎯 Recommended Mode: {recommended_mode}")
        
        # Check database
        if self.db_path.exists():
            print(f"✅ Database: {self.db_path}")
        else:
            print(f"❌ Database: {self.db_path} (not found)")
        
        print("\nAvailable Applications:")
        print("-" * 70)
        
        for mode, config in self.app_configs.items():
            app_file = self.base_dir / config['file']
            file_status = "✅" if app_file.exists() else "❌"
            
            # Check dependencies for FastAPI modes
            deps_status = ""
            if config['framework'] == 'fastapi':
                deps_ok = self.check_dependencies(mode)
                deps_status = "✅ deps" if deps_ok else "❌ deps"
            
            marker = " [RECOMMENDED]" if mode == recommended_mode else ""
            
            print(f"{file_status} {deps_status} {mode}: {config['name']}{marker}")
            print(f"    📂 File: {config['file']}")
            print(f"    🔧 Framework: {config['framework']}")
            print(f"    🔗 Port: {config['port']}")
            print(f"    📝 Description: {config['description']}")
            print()
        
        print("=" * 70 + "\n")

def main():
    """Main entry point"""
    launcher = MVidarrLauncherV2()
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == 'status':
            launcher.show_status()
            return
        elif command in launcher.app_configs:
            success = launcher.launch_application(command)
            if not success:
                sys.exit(1)
        elif command in ['help', '-h', '--help']:
            print("🎵 MVidarr Smart Launcher v2")
            print("\nUsage:")
            print("  python3 app_launcher_v2.py [command]")
            print("\nCommands:")
            print("  (no args)           - Auto-detect and launch appropriate application")
            print("  status              - Show current configuration and available apps")
            print("  flask_simple_auth   - Force launch Flask simple authentication")
            print("  flask_full_auth     - Force launch Flask full authentication")
            print("  fastapi_hybrid      - Force launch FastAPI hybrid mode (migration)")
            print("  fastapi_full        - Force launch FastAPI full mode")
            print("  help                - Show this help message")
            print("\nExamples:")
            print("  python3 app_launcher_v2.py")
            print("  python3 app_launcher_v2.py status")
            print("  python3 app_launcher_v2.py fastapi_hybrid")
            return
        else:
            logger.error(f"Unknown command: {command}")
            logger.info("Use 'help' to see available commands")
            sys.exit(1)
    else:
        success = launcher.launch_application()
        if not success:
            sys.exit(1)

if __name__ == '__main__':
    main()