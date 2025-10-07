# MVidarr SystemD Service Integration

## FastAPI Migration Service Support

The MVidarr systemd service has been updated to support the FastAPI migration with intelligent application detection and launching.

## Service Files

### 1. `mvidarr.service` (Updated)
- **Primary service file** - Updated to use smart launcher v2
- **Hybrid support** - Automatically detects FastAPI migration status
- **Backward compatible** - Falls back to Flask when appropriate

### 2. `mvidarr-v2.service` (New)
- **Next-generation service** - Optimized for FastAPI/Flask hybrid operations
- **Enhanced resource limits** - Better memory and process limits for async operations
- **Comprehensive environment** - Full FastAPI + Flask environment variables

### 3. `app_launcher_v2.py` (New Smart Launcher)
- **Migration detection** - Reads `MILESTONE_ROADMAP.md` to determine migration phase
- **Dependency checking** - Verifies FastAPI dependencies before startup
- **Multi-framework support** - Handles Flask, FastAPI, and hybrid modes

## Migration Phases & Service Behavior

### **Phase 1: FastAPI Core (CURRENT)**
- **Service starts**: FastAPI on port 8000 (hybrid mode)
- **Flask availability**: Flask still accessible on port 5000 separately
- **Job system**: Native asyncio processing via FastAPI
- **Web interface**: Still uses Flask templates

### **Phase 2: API Migration (NEXT)**
- **Service starts**: FastAPI hybrid mode
- **Critical APIs**: Migrated to FastAPI endpoints
- **Job system**: Full FastAPI integration
- **Web interface**: Still uses Flask templates

### **Phase 3: Full Migration (FUTURE)**
- **Service starts**: FastAPI on port 5000 (full mode)
- **Web interface**: Migrated to FastAPI with templates
- **Flask**: Completely replaced

## Installation & Usage

### Install New Service (Recommended)

```bash
# Copy service files to systemd
sudo cp /home/mike/mvidarr/mvidarr.service /etc/systemd/system/
sudo cp /home/mike/mvidarr/mvidarr-v2.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Enable and start service
sudo systemctl enable mvidarr.service
sudo systemctl start mvidarr.service

# Check status
sudo systemctl status mvidarr.service
```

### Manual Service Testing

```bash
# Test launcher status
cd /home/mike/mvidarr
python app_launcher_v2.py status

# Test FastAPI hybrid mode
python app_launcher_v2.py fastapi_hybrid

# Test automatic detection
python app_launcher_v2.py
```

## Service Features

### Intelligent Application Detection

The service automatically detects:
- ✅ **Migration Status** - Reads MILESTONE_ROADMAP.md Phase status
- ✅ **Authentication Mode** - Checks database settings
- ✅ **Dependencies** - Verifies FastAPI/Flask requirements
- ✅ **File Availability** - Ensures application files exist

### Environment Variables

```bash
# Flask Support
FLASK_ENV=production
PYTHONPATH=/home/mike/mvidarr

# FastAPI Support  
FASTAPI_ENV=production
UVICORN_HOST=0.0.0.0
UVICORN_PORT=8000
ASYNC_MODE=enabled
JOB_WORKERS=3

# Virtual Environment
PATH=/home/mike/mvidarr/venv/bin:/usr/local/bin:/usr/bin:/bin
```

### Enhanced Resource Limits

```bash
# File descriptors for async operations
LimitNOFILE=65536

# Process limits for background workers
LimitNPROC=8192

# Memory limits for job processing
MemoryHigh=2G
MemoryMax=4G
```

## Troubleshooting

### Check Service Status

```bash
# Service status and logs
sudo systemctl status mvidarr.service
sudo journalctl -u mvidarr.service -f

# Launcher status
cd /home/mike/mvidarr
python app_launcher_v2.py status
```

### Common Issues

**Issue**: FastAPI dependencies not found
```bash
# Solution: Install FastAPI dependencies
cd /home/mike/mvidarr
source venv/bin/activate
pip install -r requirements-fastapi.txt
```

**Issue**: Service fails to start
```bash
# Check application files
ls -la /home/mike/mvidarr/fastapi_app.py
ls -la /home/mike/mvidarr/app.py

# Check permissions
sudo chown -R mike:mike /home/mike/mvidarr
```

**Issue**: Wrong application mode detected
```bash
# Force specific mode
sudo systemctl edit mvidarr.service

# Add override:
[Service]
ExecStart=
ExecStart=/home/mike/mvidarr/venv/bin/python /home/mike/mvidarr/app_launcher_v2.py fastapi_hybrid
```

## Migration Progress Tracking

The service integrates with the milestone roadmap system:

- **Reads**: `MILESTONE_ROADMAP.md` for Phase completion status
- **Detects**: FastAPI migration progress automatically
- **Adapts**: Service behavior based on migration phase
- **Logs**: Migration status in service logs

## Service Management

```bash
# Service control
sudo systemctl start mvidarr.service
sudo systemctl stop mvidarr.service
sudo systemctl restart mvidarr.service
sudo systemctl reload mvidarr.service

# Enable/disable
sudo systemctl enable mvidarr.service
sudo systemctl disable mvidarr.service

# Check status
sudo systemctl status mvidarr.service
sudo systemctl is-active mvidarr.service
```

## Next Steps

1. **Install updated service** using the commands above
2. **Test service startup** to verify FastAPI hybrid mode
3. **Monitor service logs** during Phase 2 migration
4. **Update service configuration** as migration progresses

---

**Note**: The service will automatically adapt as the FastAPI migration progresses through Phase 2 and Phase 3, requiring minimal manual intervention.