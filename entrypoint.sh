#!/bin/bash
set -e

echo "=============================================="
echo "🚀 MVIDARR ENTRYPOINT 🚀"
echo "=============================================="
echo "📅 Start time: $(date)"
echo "👤 User: $(whoami)"
echo "📁 Directory: $(pwd)"
echo "🐧 Hostname: $(hostname)"
echo "=============================================="

# Configure user permissions (PUID/PGID)
PUID=${PUID:-1000}
PGID=${PGID:-1000}
echo "🔧 Configuring user permissions (PUID=$PUID, PGID=$PGID)..."
usermod -u "$PUID" mvidarr 2>/dev/null || true
groupmod -g "$PGID" mvidarr 2>/dev/null || true

# Create required directories
echo "📁 Creating required directories..."
mkdir -p /app/data/database \
         /app/data/thumbnails/artists \
         /app/data/cache \
         /app/data/downloads \
         /app/data/logs \
         /app/data/musicvideos \
         /app/data/music_videos

# Set proper permissions
echo "🔒 Setting directory permissions..."
chown -R "$PUID:$PGID" /app/data /app/logs
touch /app/data/database/.initialized || true

# Set umask
UMASK_SET=${UMASK_SET:-022}
umask "$UMASK_SET"

# Wait for MariaDB and Redis to be ready
echo "⏳ Waiting for MariaDB and Redis to be ready..."
timeout=180
count=0
while [ $count -lt $timeout ]; do
    mariadb_ready=false
    redis_ready=false

    nc -z "${DB_HOST:-mariadb}" "${DB_PORT:-3306}" 2>/dev/null && mariadb_ready=true
    nc -z redis 6379 2>/dev/null && redis_ready=true

    if [ "$mariadb_ready" = true ] && [ "$redis_ready" = true ]; then
        echo "✅ MariaDB and Redis are ready"
        break
    fi

    echo "Services not ready (MariaDB: $mariadb_ready, Redis: $redis_ready), waiting... ($count/$timeout seconds)"
    sleep 3
    count=$((count + 3))
done

if [ $count -ge $timeout ]; then
    echo "❌ Services failed to start within timeout ($timeout seconds)"
    exit 1
fi

# Initialize database if needed
echo "🗄️ Checking database initialization..."
if [ ! -f /app/data/database/.initialized ]; then
    echo "🔧 Database not initialized - creating tables..."
    # Use Python to initialize the database through the app's init_db function
    python3 -c "
import sys
sys.path.insert(0, '/app/src')
print('Importing database initialization module...')
try:
    from src.database.init_db import initialize_database
    print('✅ Successfully imported initialize_database')
    result = initialize_database()
    if result:
        print('✅ Database initialized successfully')
    else:
        print('⚠️ Database initialization returned False')
except ImportError as e:
    print(f'❌ Import failed: {e}')
    print('Trying alternative import...')
    try:
        from database.init_db import create_tables
        print('✅ Using create_tables function')
        success = create_tables()
        print(f'Database creation result: {success}')
    except Exception as e2:
        print(f'❌ Alternative import also failed: {e2}')
        exit(1)
except Exception as e:
    print(f'❌ Database initialization error: {e}')
    import traceback
    traceback.print_exc()
    exit(1)
" 
    if [ $? -eq 0 ]; then
        echo "✅ Database initialization completed successfully"
        touch /app/data/database/.initialized
    else
        echo "❌ Database initialization failed - check logs above"
        echo "🔄 Attempting to start application anyway (database may exist)..."
    fi
else
    echo "✅ Database already initialized (marker file exists)"
fi

# Run database migrations
echo "🔄 Running database migrations..."
python3 -c "
import sys
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/src')
print('Running database migrations...')
try:
    from src.database.migrations import run_migrations
    print('✅ Migration module loaded')
    result = run_migrations()
    if result:
        print('✅ Migrations completed successfully')
    else:
        print('⚠️ No pending migrations')
except ImportError as e:
    print(f'⚠️ Migration module not found: {e}')
    print('Skipping migrations - will run during database init')
except Exception as e:
    print(f'⚠️ Migration error: {e}')
    print('Continuing with application startup...')
"

# Start the application
echo "🚀 Starting MVidarr with supervisord (FastAPI + Celery)..."
echo "📍 Working directory: $(pwd)"
echo "🐍 Python path: $PYTHONPATH"

# Check if a command was passed as arguments
if [ "$#" -gt 0 ]; then
    echo "▶️ Executing custom command: $@"
    exec "$@"
else
    # Default: Start supervisord to manage FastAPI + Celery
    echo "▶️ Executing: /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf"
    exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf
fi