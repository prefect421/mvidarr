# Installation Wizard Specification - v1.0.0

## Problem Statement

Currently, new users face multiple challenges when setting up MVidarr:
1. No guided setup process - users must manually configure everything
2. No validation that required APIs are configured correctly
3. Directory paths may not be set or validated
4. Initial video import is unreliable (timeouts, duplicates, unclear progress)
5. No clear indication of what's required vs optional
6. Easy to miss critical setup steps

**Result:** Poor first-run experience, setup frustration, and unreliable initial data loading.

## Proposed Solution: First-Run Installation Wizard

A multi-step wizard that guides users through complete MVidarr setup:
- Automatically launches on first run
- Validates each configuration step
- Tests API connections before proceeding
- Performs reliable initial video import
- Provides clear progress and feedback

---

## User Flow

### Step 1: Welcome & Detection
**Trigger:** First time container starts OR database is empty
- Welcome message
- Brief overview of wizard steps
- Estimated time: 5-15 minutes
- Options:
  - "Start Setup" (recommended)
  - "Skip Wizard" (advanced users) - with warning

### Step 2: Admin Account Creation
- Create first admin user
- Username (required)
- Password (required, with strength indicator)
- Email (optional)
- Validation:
  - Username not taken
  - Password meets requirements
  - Test database write

### Step 3: Directory Configuration
- **Music Videos Directory** (required)
  - Default: `/app/data/musicvideos`
  - Validate: exists, readable, writable
  - Show video count in directory
  - Create if doesn't exist (with permission)

- **Thumbnails Directory** (auto-configured)
  - Default: `/app/data/thumbnails`
  - Create automatically

- **Download Directory** (auto-configured)
  - Default: `/app/data/downloads`
  - Create automatically

- **Validation Tests:**
  - Directory exists
  - Read permission
  - Write permission (test file creation)
  - Scan for video files
  - Show preview: "Found 217 video files ready to import"

### Step 4: API Configuration (Optional but Recommended)

#### IMVDb API (Metadata)
- Explanation: "Get rich metadata (year, director, genres) for your videos"
- Input: API Key field
- Link: "Get free API key from IMVDb.com"
- Test connection button
- Options:
  - Configure now (recommended)
  - Skip and add later
- Validation:
  - Test API key with sample request
  - Show success/failure clearly

#### YouTube Cookies (Downloads)
- Explanation: "Enable downloading age-restricted and member-only videos"
- File upload: cookies.txt
- Link: "How to export cookies from browser"
- Test authentication
- Options:
  - Upload now (recommended for downloaders)
  - Skip (can still download public videos)
- Validation:
  - Test cookie file format
  - Verify YouTube authentication

### Step 5: Initial Video Import

**Scan Results:**
- "Found 217 video files in /app/data/musicvideos"
- "2 artists detected"
- "Ready to import"

**Import Options:**
- ⚡ Quick Import (no metadata) - "Fast, add metadata later" - ~1 min
- 📋 Full Import (with metadata) - "Fetch IMVDb data during import" - ~5-10 min
- ⏭️  Skip Import - "Import videos later from Settings"

**Import Process:**
- Real-time progress bar
- Current file being processed
- Status messages:
  ```
  Importing: Artist Name - Song Title ✓
  Fetching metadata from IMVDb... ✓
  Downloading thumbnail... ✓
  [45/217] Processing...
  ```
- WebSocket updates (continues if browser closed)
- Pause/Resume capability
- Error handling with skip/retry options

**Import Summary:**
- Total processed: 217
- Successfully imported: 215
- Already existed: 0
- Failed: 2 (with details)
- Artists created: 45
- Metadata fetched: 198
- Thumbnails downloaded: 203

### Step 6: Completion & Next Steps

**Setup Complete!** 🎉

**Summary:**
- ✅ Admin account created
- ✅ Directories configured
- ✅ IMVDb API connected (or ⚠️ Not configured)
- ✅ YouTube cookies uploaded (or ⚠️ Not configured)
- ✅ 215 videos imported

**Next Steps:**
- [View Your Videos] - Go to videos page
- [Download More Videos] - Add new videos
- [Configure Advanced Settings] - Optional settings
- [Read Documentation] - Learn more

**Option to:**
- Show this wizard again (from Settings)
- Export configuration

---

## Technical Requirements

### Backend Implementation

#### 1. Wizard State Management
```python
# Database model
class WizardState:
    id: int
    current_step: str  # welcome, admin, directories, apis, import, complete
    completed_steps: List[str]
    configuration: JSON  # Store step data
    started_at: datetime
    completed_at: datetime
    skipped: bool
```

#### 2. API Endpoints
- `GET /api/wizard/status` - Check if wizard needed
  ```json
  {
    "required": true,
    "reason": "first_run",
    "current_step": "welcome"
  }
  ```

- `GET /api/wizard/steps` - Get wizard steps and progress
- `POST /api/wizard/steps/{step_id}` - Complete a step
- `POST /api/wizard/validate/{validation_type}` - Validate inputs
  - `directory_check`
  - `api_key_test`
  - `cookie_test`
- `POST /api/wizard/import` - Start video import
- `GET /api/wizard/import/status` - Check import progress
- `POST /api/wizard/skip` - Skip wizard (mark as completed)
- `POST /api/wizard/reset` - Restart wizard (admin only)

#### 3. Validation Functions
```python
def validate_directory(path: str) -> Dict:
    """Check directory exists, is readable/writable, scan for videos"""
    return {
        "valid": True,
        "exists": True,
        "readable": True,
        "writable": True,
        "video_count": 217,
        "sample_files": [...]
    }

def test_imvdb_connection(api_key: str) -> Dict:
    """Test IMVDb API key"""
    return {
        "valid": True,
        "message": "API key verified",
        "rate_limit": "1000 requests/day"
    }

def test_youtube_cookies(cookies_file: str) -> Dict:
    """Test YouTube authentication"""
    return {
        "valid": True,
        "authenticated": True,
        "account": "user@example.com"
    }
```

#### 4. Import Engine (New, Reliable)
```python
class WizardVideoImporter:
    """Dedicated importer for wizard - reliable, no duplicates"""

    def import_videos(self, options: Dict) -> ImportJob:
        """
        - Atomic operations (rollback on failure)
        - Proper duplicate detection by file path
        - Real-time progress updates via WebSocket
        - Resumable if interrupted
        - Clear error reporting
        """
        pass
```

#### 5. First-Run Detection
```python
def check_first_run() -> bool:
    """Check if wizard should run"""
    checks = [
        not admin_user_exists(),
        database_is_empty(),
        wizard_not_completed(),
        no_videos_in_database()
    ]
    return any(checks)
```

### Frontend Implementation

#### 1. Wizard Router Guard
```javascript
// Check on every route if wizard needed
router.beforeEach((to, from, next) => {
    if (to.path !== '/wizard' && wizardRequired()) {
        next('/wizard');
    } else {
        next();
    }
});
```

#### 2. Wizard Component Structure
```
/wizard
  ├── WizardContainer.vue (main layout, progress tracking)
  ├── steps/
  │   ├── WelcomeStep.vue
  │   ├── AdminAccountStep.vue
  │   ├── DirectoryStep.vue
  │   ├── APIConfigStep.vue
  │   ├── VideoImportStep.vue
  │   └── CompletionStep.vue
  ├── components/
  │   ├── StepProgress.vue (progress indicator)
  │   ├── DirectoryValidator.vue
  │   ├── APITester.vue
  │   └── ImportProgress.vue (real-time updates)
```

#### 3. State Management
```javascript
// Vuex/Pinia store
const wizardStore = {
    state: {
        currentStep: 0,
        completedSteps: [],
        config: {
            admin: {},
            directories: {},
            apis: {},
            import: {}
        }
    },
    actions: {
        async validateStep(step) {},
        async saveStep(step, data) {},
        async skipWizard() {}
    }
}
```

#### 4. Real-time Import Updates
```javascript
// WebSocket connection for import progress
const importSocket = new WebSocket('/ws/wizard-import');
importSocket.onmessage = (event) => {
    const progress = JSON.parse(event.data);
    updateProgress(progress);
    // {
    //   current: 45,
    //   total: 217,
    //   current_file: "Artist - Song.mp4",
    //   status: "processing",
    //   errors: []
    // }
};
```

### Database Schema

```sql
-- Wizard state tracking
CREATE TABLE wizard_state (
    id INTEGER PRIMARY KEY,
    current_step VARCHAR(50),
    completed_steps JSON,
    configuration JSON,
    started_at DATETIME,
    completed_at DATETIME,
    skipped BOOLEAN DEFAULT FALSE
);

-- Import job tracking (separate from regular jobs)
CREATE TABLE wizard_import_jobs (
    id INTEGER PRIMARY KEY,
    wizard_state_id INTEGER,
    status VARCHAR(50),  -- queued, processing, completed, failed
    total_files INTEGER,
    processed_files INTEGER,
    successful INTEGER,
    failed INTEGER,
    errors JSON,
    started_at DATETIME,
    completed_at DATETIME
);
```

---

## User Stories

### As a first-time user:
1. I want to be guided through setup so I don't miss critical configuration
2. I want to test my API keys work before proceeding
3. I want to see how many videos will be imported before starting
4. I want clear progress during video import so I know it's working
5. I want to skip optional steps and configure them later
6. I want the import to continue even if I close my browser

### As an admin:
1. I want to reset and re-run the wizard if needed
2. I want to validate directory permissions before import fails
3. I want clear error messages if something goes wrong
4. I want to skip the wizard if I'm doing advanced setup

### As a developer:
1. I want the wizard code to be modular and testable
2. I want to add new wizard steps easily
3. I want validation to be reusable outside the wizard
4. I want the import engine to be reliable and maintainable

---

## Acceptance Criteria

### Must Have:
- ✅ Wizard automatically launches on first run
- ✅ All required configuration completed before proceeding
- ✅ Directory validation with clear error messages
- ✅ API key testing before saving
- ✅ Duplicate-free video import
- ✅ Real-time progress updates during import
- ✅ Clear completion summary
- ✅ Ability to skip wizard (with warning)
- ✅ Mobile-responsive design

### Should Have:
- ✅ Resume wizard if interrupted
- ✅ Back button to previous steps
- ✅ Export configuration
- ✅ Inline help/documentation
- ✅ Import continues if browser closed (WebSocket)

### Could Have:
- ✅ Dark mode wizard theme
- ✅ Estimated time remaining for import
- ✅ Pre-flight checks before each step
- ✅ Configuration import from file
- ✅ Wizard tutorial video

---

## Dependencies

### Existing Systems:
- Database models (Artist, Video, Download)
- IMVDb service
- File scanning service
- Background job queue (optional for import)
- WebSocket system

### New Systems Required:
- Wizard state management
- First-run detection middleware
- Validation service
- Dedicated import engine (reliable, no duplicates)
- Wizard API endpoints
- Wizard frontend components

---

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)
- Wizard state management
- First-run detection
- Basic API endpoints
- Frontend wizard container

### Phase 2: Configuration Steps (Week 2)
- Admin account creation
- Directory validation
- API configuration
- Step navigation

### Phase 3: Import Engine (Week 3)
- Reliable import implementation
- Duplicate detection
- Progress tracking
- Error handling

### Phase 4: Polish & Testing (Week 4)
- Real-time updates
- Mobile responsiveness
- Error recovery
- User testing

---

## Testing Requirements

### Unit Tests:
- Directory validation logic
- API key testing
- Duplicate detection
- Import engine

### Integration Tests:
- Complete wizard flow
- API endpoint integration
- WebSocket communication
- Database transactions

### User Acceptance Tests:
- First-run experience
- Error scenarios
- Mobile devices
- Different configurations

---

## Success Metrics

- 95%+ first-run success rate
- Zero duplicate videos on import
- < 5 second response time per step
- Clear error messages for all failure modes
- 90%+ user satisfaction in post-setup survey

---

## Related Issues

- #XXX - Current indexing reliability issues
- #XXX - Duplicate video detection
- #XXX - First-run user experience
- #XXX - API configuration validation

---

## Future Enhancements

- Multi-language wizard
- Video import presets (music videos, concerts, etc.)
- Integration with external storage (S3, etc.)
- Automated metadata backfill after import
- Import progress email notifications
