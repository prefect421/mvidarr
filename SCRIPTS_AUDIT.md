# Scripts Directory Audit - Phase 5

**Date**: 2025-10-29
**Status**: 🔄 In Progress

---

## Executive Summary

The `scripts/` directory contains 90+ files and 11 subdirectories with mixed purposes: active utilities, obsolete one-time fixes, development helpers, and archived code. Most scripts lack documentation.

**Findings**:
- **1 script** actively used and documented (`reset_stuck_downloads.py`)
- **~15 scripts** likely still needed but undocumented
- **~60+ scripts** appear obsolete or are one-time fixes
- **11 subdirectories** with varying levels of organization

---

## Currently Active Scripts

### ✅ Production Use
| Script | Purpose | Status | Action |
|--------|---------|--------|--------|
| `reset_stuck_downloads.py` | Resets stuck downloads on startup | ✅ In use (mvidarr.service) | Keep, documented |
| `manage-services.sh` | Service management utility | ✅ Active | Keep, needs documentation |
| `update_version.sh` | Updates version metadata | ✅ Referenced in CLAUDE.md | Keep, needs documentation |
| `health_check.sh` | System health monitoring | ✅ Likely active | Keep, needs documentation |

### 🔧 Utility Scripts (Likely Active)
| Script | Purpose | Status | Action |
|--------|---------|--------|--------|
| `backfill_video_years.py` | Backfills video year metadata | 🟡 Utility | Review, document if keeping |
| `backfill_year_from_descriptions.py` | Year extraction from descriptions | 🟡 Utility | Review, document if keeping |
| `backfill_year_from_info_json.py` | Year extraction from YouTube metadata | 🟡 Utility | Review, document if keeping |
| `backfill_year_from_upload_date.py` | Year extraction from upload date | 🟡 Utility | Review, document if keeping |
| `install.sh` | Installation script | 🟡 Setup | Keep, verify documentation |
| `install_service.sh` | Service installation | 🟡 Setup | Keep, verify documentation |
| `setup_database.sh` | Database setup | 🟡 Setup | Keep, verify documentation |
| `setup_production.py` | Production environment setup | 🟡 Setup | Keep, verify documentation |
| `generate_secret_key.py` | Secret key generation | 🟡 Setup | Keep, needs documentation |

---

## Potentially Obsolete Scripts

### 🗑️ Development/AI Helper Scripts (Likely Obsolete)
- `code_review_agent.py` + `code_review_config.json`
- `programmer_agent.py` + `programmer_agent_config.json`
- `project_manager_agent.py` + `project_manager_config.json`
- `setup_code_review.sh`
- `setup_programmer_agent.sh`
- `setup_project_manager.sh`

**Recommendation**: Archive - These were development helpers, not production utilities

### 📸 Screenshot/Documentation Scripts (Likely Obsolete)
- `capture_screenshots.py`
- `enhanced_pdf_generator.py`
- `generate_pdf_docs.py`
- `phase3_screenshots.py`
- `final_screenshots.py`
- `quick_screenshots.py`
- `simple_screenshot_capture.py`

**Recommendation**: Archive - Documentation generation likely no longer needed

### 🔄 Restart Scripts (Superseded by Systemd)
- `admin_restart.py`
- `improved_restart.py`
- `restart_app.py`

**Recommendation**: Archive - Systemd handles service restarts now

### 🚀 Deployment Scripts (Status Unknown)
- `deploy-kubernetes.sh`
- `deploy-selfhosted.sh`
- `cron-scheduler.sh`
- `scheduler-service.py`

**Recommendation**: Review with user - may be obsolete if not using Kubernetes/cron

### 🛠️ One-Time Fix Scripts
- `fix_simple_auth_credentials.py`
- `fix_missing_videos.py`
- `fix_download_queue_issue.py`
- `fix_artist_folder_paths.py`
- `fix_artists_list.py`
- `fix_download_completion.py`
- `fix_missing_video_metadata.py`

**Recommendation**: Move to `archive/` - These were one-time data fixes

### 🧪 Development/Testing Scripts
- `focused_phase3.py`
- `essential_remaining.py`
- `final_push.py`
- `build-context-analyzer.sh`
- `docker-size-monitor.sh`

**Recommendation**: Archive - Development phase scripts

---

## Subdirectory Analysis

### 📁 `archive/` (3 files)
- `get_cookies.py`
- `test_formats.py`
- `old_server.py`

**Status**: ✅ Already archived
**Action**: Leave as-is

### 📁 `fixes/` (13 files)
All appear to be one-time fix scripts for data cleanup:
- Artist identification scripts
- Video title fix scripts
- Lyrics video checks

**Status**: 🗑️ One-time use completed
**Action**: Consider consolidating into `archive/fixes/` or removing

### 📁 `screenshots/` (3 files)
- `capture_screenshots.py`
- `enhanced_capture.py`
- `setup_and_capture.sh`

**Status**: 🗑️ Likely obsolete
**Action**: Move to `archive/screenshots/` or remove

### 📁 `migrations/` (8 files)
Database migration scripts for adding tables/columns

**Status**: ⚠️ **CRITICAL - DO NOT REMOVE**
**Action**: Keep - These may be needed for fresh installs or rollbacks

### 📁 `testing/` (2 files)
- `manual_test_checklist.py`
- `run_comprehensive_tests.py`

**Status**: 🔄 Review needed
**Action**: Check if still relevant after Phase 4 Playwright tests

### 📁 `setup/`, `deployment/`, `monitoring/`, `release/`, `downloads/`
**Status**: 🔄 Review needed
**Action**: Check contents and usage

---

## Recommendations

### Immediate Actions (Phase 5)

1. **Documentation Priority** - Document these active scripts in `scripts/README.md`:
   - `manage-services.sh` - Service management
   - `update_version.sh` - Version metadata updates
   - `health_check.sh` - Health monitoring
   - `install.sh` / `install_service.sh` - Installation
   - `setup_database.sh` - Database setup
   - `generate_secret_key.py` - Secret key generation

2. **Archive These Obsolete Scripts**:
   - All AI/agent scripts (6 files)
   - All screenshot/PDF scripts (7 files)
   - All restart scripts (3 files)
   - Phase-specific development scripts (4 files)
   - **Total**: ~20 files to archive

3. **Review with User**:
   - Deployment scripts (Kubernetes, cron, scheduler)
   - Backfill scripts (may still be useful utilities)
   - Testing scripts (may be superseded by Playwright)

4. **Critical - Do Not Touch**:
   - `migrations/` directory - Database migrations needed for fresh installs
   - `reset_stuck_downloads.py` - Active production use

### Long-term Actions (Post-1.0)

1. Create organized subdirectory structure:
   ```
   scripts/
   ├── production/      # Active production scripts
   ├── utilities/       # Maintenance/admin utilities
   ├── setup/           # Installation scripts
   ├── migrations/      # Database migrations
   ├── archive/         # Historical/obsolete scripts
   └── README.md        # Comprehensive documentation
   ```

2. Add header comments to all active scripts with:
   - Purpose
   - Usage examples
   - Dependencies
   - Last updated date

---

## Next Steps

1. ✅ Complete this audit document
2. 🔄 Review recommendations with user
3. 🔄 Archive obsolete scripts
4. 🔄 Update `scripts/README.md` with active script documentation
5. 🔄 Update MILESTONE_0.9.9_CLEANUP.md with Phase 5 completion

---

## Files Requiring User Decision

| Script | Question | Options |
|--------|----------|---------|
| `deploy-kubernetes.sh` | Is Kubernetes deployment still used? | Keep / Archive |
| `deploy-selfhosted.sh` | Is this deployment method used? | Keep / Archive |
| `scheduler-service.py` | Is cron scheduling used? | Keep / Archive |
| `backfill_*.py` (4 files) | Should these be kept as utilities? | Keep / Archive |
| `testing/` scripts | Superseded by Playwright tests? | Keep / Archive |

**Estimated Cleanup Impact**:
- Files to archive: 20-30
- Files needing documentation: 8-10
- Current files: 90+
- Target files after cleanup: 50-60 (well-organized)
