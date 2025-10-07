#!/usr/bin/env python3
"""
MVidarr Flask Application - Port 5010
Dedicated Flask frontend server for hybrid mode
"""

import logging
import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import the existing Flask application factory
from app import create_app


def main():
    """Main entry point for Flask on port 5010"""
    # Create the Flask application
    app = create_app()
    
    # Override port to 5010 for hybrid mode
    port = 5010
    host = "0.0.0.0"
    
    app.logger.info(f"🌶️  Starting MVidarr Flask Frontend on {host}:{port}")
    app.logger.info("🔧 Running in hybrid mode alongside FastAPI backend")
    app.logger.info("⚡ FastAPI backend available at http://192.168.1.152:5000")
    
    try:
        # Use SocketIO's run method if available, otherwise use Flask's run method
        if hasattr(app, 'socketio') and app.socketio is not None:
            app.logger.info("🔌 Starting with SocketIO support for real-time updates")
            app.socketio.run(
                app, 
                host=host, 
                port=port, 
                debug=app.config.get("DEBUG", False),
                allow_unsafe_werkzeug=True  # Allow for development
            )
        else:
            app.logger.info("🔌 Starting without SocketIO support")
            app.run(
                host=host, 
                port=port, 
                debug=app.config.get("DEBUG", False),
                threaded=True  # Enable threading for better concurrency
            )
    except Exception as e:
        app.logger.error(f"❌ Failed to start Flask application: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()