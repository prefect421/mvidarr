# Installation Wizard Implementation Status
**Issue #163** - First-Run Installation Wizard for v1.0.0
**Status:** Phase 1 & 2 Complete ✅

---

## Implementation Complete

### Phase 1: Backend Infrastructure ✅ (Completed: 2025-11-11)

#### Database Layer
- **Model**: `WizardState` in `src/database/models.py:937`
  - Tracks wizard progress and configuration
  - Stores admin account info, directory paths, API keys
  - Records import job status and results
  - Timestamped state transitions

- **Enums**:
  - `WizardStatus`: NOT_STARTED, IN_PROGRESS, COMPLETED, SKIPPED
  - `WizardStep`: WELCOME, ADMIN_ACCOUNT, DIRECTORIES, API_CONFIG, VIDEO_IMPORT, COMPLETE

- **Migration**: `alembic/versions/79107aab2257_add_wizard_state_table_for_installation_.py`
  - Applied to database ✅
  - Creates `wizard_state` table with full schema
  - Includes indexes for performance

#### API Endpoints (`src/api/fastapi/wizard.py`)
All endpoints are **unauthenticated** (first-run before users exist):

1. **GET `/api/wizard/status`**
   - Returns current wizard state
   - Auto-creates state if not exists
   - Response: `WizardStateResponse` with completion percentage, step status, config data

2. **POST `/api/wizard/start`**
   - Initializes wizard
   - Sets status to IN_PROGRESS
   - Advances to WELCOME step

3. **POST `/api/wizard/steps/{step_id}/complete`**
   - Marks step as complete
   - Stores configuration data
   - Advances to next step
   - Auto-completes wizard when all steps done

4. **POST `/api/wizard/skip`**
   - Skips wizard entirely
   - Marks status as SKIPPED
   - Allows manual configuration

5. **POST `/api/wizard/validate-directory`**
   - Validates directory exists, readable, writable
   - Scans for video files (.mp4, .mkv, .avi, .mov, .webm, .flv)
   - Returns video count
   - Response: `DirectoryValidationResponse`

6. **POST `/api/wizard/test-api`**
   - Tests IMVDb API key with sample request
   - Validates YouTube cookies format
   - Response: `APITestResponse` with success/error

7. **POST `/api/wizard/import/start`**
   - Creates background job for video import
   - Queues `VIDEO_INDEX_ALL` job with HIGH priority
   - Flags as wizard import for tracking
   - Returns job ID for progress polling

#### Middleware (`src/api/fastapi/wizard_middleware.py`)
**Status:** ✅ Active in `fastapi_app.py:461`

- **FirstRunDetectionMiddleware**:
  - Checks wizard completion on every request
  - Redirects web requests to `/wizard` if not completed
  - Returns 503 JSON for API requests before completion
  - Bypasses check for:
    - `/api/wizard/*` - Wizard API endpoints
    - `/static/*` - Static assets
    - `/health`, `/api/health` - Health checks
    - `/docs`, `/redoc`, `/openapi.json` - OpenAPI docs

- **Environment variable**: `DISABLE_WIZARD_MIDDLEWARE=true` to bypass (dev/testing)

---

### Phase 2: Frontend Implementation ✅ (Completed: 2025-11-11)

#### HTML Template (`frontend/templates/wizard.html`)
**Complete 6-step wizard with embedded CSS**

**Step 1: Welcome** 👋
- MVidarr introduction
- Overview of wizard steps
- Estimated time: 5-15 minutes
- "Get Started" or "Skip Setup" options

**Step 2: Admin Account** 👤
- Username (required, min 3 chars)
- Email (required, validated)
- Password (required, min 8 chars, strength validation)
- Confirm password (must match)
- Creates admin user via `/api/admin/users`

**Step 3: Directories** 📁
- Music videos directory path input
- Default: `/app/data/musicvideos`
- "Validate Directory" button
- Real-time validation with video count
- Shows: exists, readable, writable, video count
- Must validate before continuing

**Step 4: API Configuration** 🔌
- **IMVDb API** (optional):
  - API key input
  - Test connection button
  - Link to get free API key
  - Visual success/error feedback

- **YouTube Cookies** (optional):
  - Textarea for cookies.txt content
  - Format validation
  - Both APIs can be skipped

**Step 5: Video Import** 🎬
- Shows video count from directory validation
- **Import options**:
  - ⚡ Quick Import (no metadata, ~1 min)
  - 📋 Full Import (with metadata, ~5-10 min)
  - ⏭️ Skip Import (do later)

- **Progress tracking**:
  - Real-time progress bar (0-100%)
  - Import statistics: Processed, Success, Failed
  - Current file being processed
  - Polls `/api/jobs/{job_id}` every 2 seconds
  - Auto-advances when complete

**Step 6: Completion** 🎉
- Configuration summary with checkmarks
- Shows what was configured vs skipped
- Links to:
  - View Your Videos
  - Configure Settings
  - Go to Dashboard

#### JavaScript Controller (`frontend/static/wizard.js`)
**Complete client-side wizard logic**

**Features**:
- Step navigation (next/previous)
- Progress indicator updates
- Form validation (email, password strength)
- Wizard state management (save/load from backend)
- API communication for all wizard steps
- Real-time import progress polling
- Error handling and user feedback

**Key Functions**:
- `nextStep()` / `previousStep()` - Navigation
- `submitAdminForm()` - Create admin account with validation
- `validateDirectory()` - Test directory and count videos
- `testIMVDb()` - Test IMVDb API connection
- `startImport()` - Queue video import job
- `pollImportProgress()` - Real-time progress updates
- `skipWizard()` - Skip entire wizard
- `completeStep()` - Mark step complete in backend

**State Management**:
- Tracks current step, completed steps, configuration
- Persists state to backend via `/api/wizard/status`
- Loads previous state on page load (resume wizard)
- Stores admin info, directories, API keys, import results

#### Styling
**Embedded CSS in wizard.html**

- **Theme support**: Light and dark themes via CSS variables
- **Responsive**: Mobile-friendly (breakpoint: 640px)
- **Components**:
  - Progress indicator with 6 steps
  - Wizard card with step animations
  - Form inputs with validation states
  - Success/error/warning message boxes
  - Validation badges (success, error, warning)
  - Progress bar for import
  - Loading spinners
  - Buttons (primary, secondary, link)

- **Animations**: Fade-in for step transitions, progress bar fills

---

## File Structure

```
src/
├── database/
│   ├── models.py                    # WizardState model (line 937)
│   └── ...
├── api/
│   └── fastapi/
│       ├── wizard.py                # Wizard API endpoints ✅
│       ├── wizard_middleware.py     # First-run detection middleware ✅
│       └── ...
├── ...

frontend/
├── templates/
│   └── wizard.html                  # Complete 6-step wizard UI ✅
└── static/
    └── wizard.js                    # Client-side wizard controller ✅

alembic/
└── versions/
    └── 79107aab2257_*.py           # Wizard database migration ✅

fastapi_app.py                       # Wizard router + middleware integrated ✅
```

---

## API Endpoints Summary

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/wizard/status` | Get wizard state | ❌ None |
| POST | `/api/wizard/start` | Start wizard | ❌ None |
| POST | `/api/wizard/steps/{id}/complete` | Complete step | ❌ None |
| POST | `/api/wizard/skip` | Skip wizard | ❌ None |
| POST | `/api/wizard/validate-directory` | Validate directory | ❌ None |
| POST | `/api/wizard/test-api` | Test API keys | ❌ None |
| POST | `/api/wizard/import/start` | Start import job | ❌ None |

---

## How It Works

### First Run Detection
1. User accesses MVidarr for the first time
2. `FirstRunDetectionMiddleware` intercepts request
3. Checks `WizardState` table for completion status
4. If not completed: Redirect to `/wizard`
5. If completed: Allow normal access

### Wizard Flow
1. **Welcome** - User clicks "Get Started"
2. **Admin Account** - Creates first admin user
3. **Directories** - Validates and saves video directory path
4. **APIs** - Optionally configures IMVDb/YouTube
5. **Import** - Queues background job to import videos
6. **Complete** - Shows summary, redirects to dashboard

### Import Process
1. User selects import type (quick/full/skip)
2. Frontend calls `/api/wizard/import/start`
3. Backend creates `VIDEO_INDEX_ALL` background job
4. Frontend polls `/api/jobs/{job_id}` every 2 seconds
5. Progress bar updates in real-time
6. On completion: Shows summary and enables "Continue"

---

## Testing Status

### Backend
- ✅ Database migration applied
- ✅ WizardState table exists
- ✅ API endpoints created and integrated
- ✅ Middleware enabled and active
- ⚠️ End-to-end testing pending

### Frontend
- ✅ HTML template created
- ✅ JavaScript controller implemented
- ✅ All 6 steps built
- ✅ Form validation included
- ⚠️ End-to-end testing pending

---

## Next Steps (Phase 3)

### Testing & Refinement
1. **End-to-end testing**
   - Test complete wizard flow
   - Verify all API calls work
   - Test validation logic
   - Test import progress polling
   - Test skip functionality

2. **Error handling improvements**
   - Better error messages
   - Retry mechanisms
   - Graceful failures

3. **UX enhancements**
   - Loading states
   - Success animations
   - Better validation feedback
   - Help tooltips

4. **Documentation**
   - User guide for wizard
   - Admin guide for troubleshooting
   - API documentation updates

---

## Configuration

### Environment Variables
- `DISABLE_WIZARD_MIDDLEWARE=true` - Disable wizard middleware (dev/testing)

### Settings
No additional settings required. Wizard auto-detects first run.

---

## Troubleshooting

### Wizard not showing
- Check `wizard_state` table exists
- Verify middleware is enabled in `fastapi_app.py`
- Check no existing completed wizard state

### Import not starting
- Verify background job queue is running
- Check directory permissions
- Verify video files exist in directory

### API tests failing
- Verify API keys are valid
- Check network connectivity
- Review API rate limits

---

## Implementation Notes

### Design Decisions
1. **No authentication for wizard endpoints**: Required since wizard runs before any users exist
2. **Embedded CSS in template**: Avoids dependency on main.css for isolated wizard experience
3. **Polling for progress**: Simpler than WebSocket for MVP
4. **Optional API configuration**: Allows users to complete wizard quickly, configure later

### Security Considerations
- Wizard endpoints are unauthenticated but only accessible before completion
- Once wizard completes, middleware blocks access
- Admin account uses standard password validation
- API keys validated before saving

### Performance
- Directory scanning uses `rglob` with file extension filtering
- Progress polling every 2 seconds (configurable)
- Video import runs in background job queue
- No blocking operations in wizard endpoints

---

## Related Issues
- **Issue #163**: First-Run Installation Wizard for v1.0.0
- **Issue #161**: Fix version.json to show correct commit hash (dependency)
- **Issue #92**: Implement Alembic database migration system (dependency)

---

## Credits
- **Implementation**: Phase 1 & 2 complete
- **Date**: 2025-11-11
- **Contributors**: Claude Code Assistant

---

**Status**: ✅ Phase 1 (Backend) & Phase 2 (Frontend) Complete
**Next**: Phase 3 (Testing & Refinement)
