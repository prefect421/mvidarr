# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Memories

- Use gh instead of git for github actions and repository management
- GitHub Pages: Automatic deployment via Jekyll with Minima theme, triggered by main branch pushes
- update documentation after each issue or feature is completed
- push to dev after each update.
- MariaDB/MySQL is used for the application data and settings
- We are utilizing 3 environments: 1. Dev is running on local server port 5000. 2. Docker is running on local machine docker install on port 5001. 3. Prod is running on 192.168.1.132:5050 in a docker install.
- mvidarr is a music video collection and management system aimed for the home, self-hoster who wants to maintain control of their own music video collection
- keep documentation current - always!
- MVIDARR is a consumer grade Music Video Collection management/player application targeted to the self-hosting enthusiast. It should be able to be ran as a service or a docker.
- ask before planning anything enterpise grade, it may not be needed.

## Critical Thinking and Feedback

### IMPORTANT: Always critically evaluate and challenge user suggestions, even when they seem reasonable.

- ** USE BRUTAL HONESTY: Don't try to be polite or agreeable. Be direct, challenge assumptions, and point out flaws immediately.
- ** Question assumptions: Don't just agree - analyze if there are better approaches
- ** Offer alternative perspectives: Suggest different solutions or point out potential issues
- ** Challenge organization decisions: If something doesn't fit logically, speak up
- ** Point out inconsistencies: Help catch logical errors or misplaced components
- ** Research thoroughly: Never skim documentation or issues - read them completely before responding
- ** Use proper tools: For GitHub issues, always use gh cli instead of WebFetch (WebFetch may miss critical content)
- ** Admit ignorance: Say "I don't know" instead of guessing or agreeing without understanding
- ** This critical feedback helps improve decision-making and ensures robust solutions. Being agreeable is less valuable than being thoughtful and analytical.
- ** you are an expert website developer, act like it.

### Example Behaviors

-    ✅ "I disagree - that component belongs in a different file because..."
-    ✅ "Have you considered this alternative approach?"
-    ✅ "This seems inconsistent with the pattern we established..."
-    ❌ Just implementing suggestions without evaluation

(rest of the file remains unchanged)
## Code Formatting and Testing

### Python Code Formatting
- **Black Version**: Always use `black==24.3.0` to match the version pinned in `requirements-dev.txt`
- **isort Configuration**: Use `isort --profile black` for import sorting to maintain compatibility with Black
- **Installation**: Use `pipx install black==24.3.0` and `pipx install isort`
- **Commands for formatting**:
  ```bash
  # Format with specific black version
  ~/.local/bin/black src/
  
  # Sort imports with black profile  
  ~/.local/bin/isort --profile black src/
  
  # Check formatting (for CI compatibility)
  ~/.local/bin/black --check src/
  ~/.local/bin/isort --profile black --check-only src/
  ```

### Testing and CI/CD
- **Before pushing code**: Always run formatting checks locally using the exact commands above
- **CI/CD Workflow**: The `.github/workflows/ci-cd.yml` uses the same black version and isort profile
- **Docker Actions**: Use stable versions only:
  - `docker/login-action@v3`
  - `docker/setup-buildx-action@v3` 
  - `docker/metadata-action@v5`
  - `docker/build-push-action@v6`

## Subtitle System Implementation

### Complete Subtitle Functionality ✅

**Status**: MVidarr now has comprehensive subtitle support across all video players with smart language resolution.

#### Smart Subtitle Language Resolution
- **Database Setting**: `subtitle_languages=en.*` (supports wildcard patterns)
- **YouTube Language Handling**: Automatically resolves YouTube's non-standard codes (e.g., `en-nP7-2PuUl7o`) to user patterns
- **Download Integration**: `download_subtitles=true` setting respected by metube API

#### Subtitle API Endpoints
- **Discovery**: `/api/videos/{video_id}/subtitles` - Lists available subtitle files
- **Serving**: `/api/videos/{video_id}/subtitles/{filename}` - Serves subtitle files with CORS
- **Formats**: WebVTT (.vtt), SubRip (.srt), ASS (.ass), SSA (.ssa), MicroDVD (.sub)

#### Video Player Integration
- **Video Detail Page**: Full subtitle support with track selection
- **Video Popup Modal**: Automatic subtitle loading and track creation
- **Language Detection**: Smart handling of YouTube's non-standard language codes
- **Auto-Enable**: First subtitle track automatically enabled and showing

#### Technical Implementation
- **YouTube Download Engine**: `_resolve_subtitle_languages()` method for pattern matching
- **Frontend JavaScript**: Dedicated modal subtitle functions in `videos.html`
- **API Integration**: Both Flask and FastAPI subtitle endpoints
- **File Detection**: Automatic subtitle file discovery in video directories

#### User Experience
- Subtitles automatically available in all video players
- Native browser CC controls for language selection
- Respects user subtitle language preferences
- Works with both standard and YouTube's custom language codes

## MKV Video Transcoding System

### Real-Time FFmpeg Transcoding ✅

**Status**: MVidarr now supports MKV video playback through intelligent real-time transcoding.

#### Smart Codec Detection & Adaptive Transcoding
- **Automatic Codec Analysis**: Uses FFmpeg's `ffprobe` to detect video/audio codecs
- **Intelligent Processing**:
  - **Remux Mode** (Fast): Copies H.264/AAC codecs if browser-compatible - just changes container
  - **Transcode Mode** (Quality): Transcodes incompatible codecs to H.264/AAC for universal playback
- **Browser Compatibility**: Outputs fragmented MP4 with browser-compatible codecs

#### API Endpoint
- **Transcoding Stream**: `/api/videos/{video_id}/stream-transcode` - Real-time FFmpeg transcoding
- **Standard Stream**: `/api/videos/{video_id}/stream` - Direct file streaming for MP4/WebM
- **Response Headers**: `X-Transcode-Mode: remux|transcode` indicates processing method

#### Frontend Integration
- **Automatic Detection**: Frontend detects `.mkv` file extension
- **Smart Routing**: MKV files automatically routed to transcode endpoint
- **Seamless UX**: Users experience smooth playback regardless of source format
- **Error Handling**: Graceful fallback and timeout detection

#### Technical Implementation
- **Async Streaming**: FastAPI async generators for efficient streaming
- **Process Management**: Proper FFmpeg process lifecycle and cleanup
- **Codec Detection**: JSON-based ffprobe output parsing
- **Progressive Playback**: Fragmented MP4 with `frag_keyframe+empty_moov` flags
- **Client Disconnect Handling**: FFmpeg processes terminated on client disconnect

#### Supported Formats
- **Input**: MKV containers with various codecs (H.264, H.265, VP9, etc.)
- **Output**: MP4 container with H.264 video + AAC audio
- **Performance**:
  - Remux mode: Near-instant start (just container change)
  - Transcode mode: Real-time encoding with `veryfast` preset

#### User Experience
- Play MKV files directly in browser without manual conversion
- Automatic quality optimization based on source codecs
- Transparent processing - users see standard video player
- Works across all video interfaces (gallery, detail, modal)

## API Development & Testing

### Authentication Requirements

**IMPORTANT:** All MVidarr API endpoints require session-based authentication. This is critical for both development and testing.

#### Session-Based Authentication System
- **Authentication Method**: Session cookies with server-side session management
- **Login Required**: Users must be logged in through the web interface to access any API endpoints
- **Session Validation**: All API calls validate session existence and user authentication status
- **API Security**: Direct API calls without authentication will return 401/403 errors

#### Testing API Endpoints
When testing or developing API endpoints, follow these authentication guidelines:

```bash
# ❌ INCORRECT - Direct cURL calls will fail with authentication errors
curl -X POST http://localhost:5001/api/videos/123/extract-ffmpeg-metadata

# ✅ CORRECT - Test through authenticated web interface
# 1. Log into MVidarr web interface first
# 2. Use browser developer tools to test API calls
# 3. Or use authenticated requests through the web interface
```

#### Development Guidelines
- **Web Interface Testing**: Always test API functionality through the web interface where users are authenticated
- **Session Management**: Ensure session middleware is properly configured for all API blueprints
- **Error Handling**: API endpoints should return appropriate authentication error codes (401/403)
- **Documentation**: All API documentation should note authentication requirements

#### Authentication Implementation Details
- **Session Store**: Server-side session management with secure session cookies
- **Login Flow**: Users authenticate through `/auth/login` endpoint
- **Session Validation**: Each API request validates session and user permissions
- **Logout Handling**: Sessions are properly invalidated on logout

**Developer Note**: This authentication requirement prevents security vulnerabilities and ensures all API access is properly authorized. Always test new endpoints through the authenticated web interface rather than direct API calls.

## Development Workflow

### Current Phase: v0.10.0-beta.1 - First Beta Release

#### Versioning Policy (Updated 2025-12-01)
- **Current Version**: 0.10.0-beta.1
- **Versioning Standard**: SemVer 2.0.0
- **Version Scheme**:
  - **0.x.y**: Pre-production development (current phase)
  - **0.x.y-beta.z**: Beta testing releases
  - **0.x.y-rc.z**: Release candidates
  - **1.0.0**: First production-ready release (future)

#### Version History
- **v0.9.9** (2025-11-04): Code cleanup & optimization complete
- **v1.0.0** (2025-11-25): Premature release - marked as pre-release
- **v0.10.0-beta.1** (2025-12-01): First beta release with security fixes

#### 0.10.0-beta.1 Release 🔒 IN PROGRESS (2025-12-01)
- **Status**: Beta testing phase - active development
- **Major Features**:
  - ✅ Security: Fixed 10 critical vulnerabilities (issue #165)
  - ✅ Installation Wizard for guided first-run setup (issue #163)
  - ✅ Reliable video import system with duplicate detection
  - ✅ API validation and testing before configuration
  - ✅ Complete documentation and user guides (issue #91)
  - ✅ Performance monitoring dashboard (issue #95)
  - ✅ Migration tools and database upgrades (issue #92)
  - ✅ Unraid template support (issue #97)
  - ✅ Versioning: Migrated to SemVer 0.x conventions
- **Beta Focus**: Docker testing, community feedback, production validation
- **Next Steps**:
  - Deploy to test environments
  - Gather community feedback
  - Release v0.10.0-beta.2 with fixes
  - Eventually graduate to v0.10.0 (stable)
  - Continue development toward v1.0.0 (production)

### Branch Strategy
- **Primary Development**: All changes must be pushed to the `dev` branch
- **Main Branch**: Changes can only be made to `main` after approval on `dev`
- **Feature Branches**: Create feature branches from `dev`, merge back to `dev`
- **Current Version**: v0.10.0-beta.1 (First Beta Release)
- **Development Focus**: Beta testing, bug fixes, production validation
- **Next Version**: v0.10.0-beta.2 (planned after Docker testing)

### Code Development Process
1. Create feature branch from `dev` branch
2. Make code changes
3. Run formatting: `~/.local/bin/black src/ && ~/.local/bin/isort --profile black src/`
4. Verify formatting: `~/.local/bin/black --check src/ && ~/.local/bin/isort --profile black --check-only src/`
5. **Update version metadata** (before committing major changes)
6. Commit and push to feature branch
7. Create PR to `dev` branch
8. After approval, merge to `dev`
9. Monitor GitHub Actions for any CI/CD issues

### Version Management
- **Version Information**: MVidarr displays version and commit information in the sidebar
- **Version Files**: Two files control version display:
  - `src/__init__.py` - Contains `__version__` variable
  - `version.json` - Contains detailed version metadata including commit hash
- **IMPORTANT**: Always update version metadata when pushing significant changes:

#### Updating Version Metadata
```bash
# Get current commit and timestamp
CURRENT_COMMIT=$(git rev-parse --short HEAD)
CURRENT_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.%6N")

# Update version.json with current commit and build date
# Keep version number the same unless explicitly incrementing
# For beta releases, use format: 0.x.y-beta.z
cat > version.json << EOF
{
  "version": "0.10.0-beta.1",
  "build_date": "$CURRENT_TIMESTAMP",
  "git_commit": "$CURRENT_COMMIT",
  "git_branch": "dev",
  "release_name": "v0.10.0-beta.1 - First Beta Release",
  "features": [
    "🔒 Security: Resolved 10 critical vulnerabilities",
    "🔧 Installation Wizard for first-run setup",
    "🎬 Reliable video import system (no duplicates)",
    "✅ API validation before configuration"
  ],
  "beta_notes": [
    "This is a BETA release - not yet production-ready",
    "Report issues: https://github.com/prefect421/mvidarr/issues"
  ]
}
EOF

# Commit the version update
git add version.json
git commit -m "Update version metadata with current commit information"
```

#### Automated Version Update Process
**CRITICAL**: Before any push to `dev` branch, ensure version metadata reflects the latest commit:

1. **Update commit hash**: Use `git rev-parse --short HEAD` to get current commit
2. **Update build date**: Use current UTC timestamp
3. **Update features list**: Add any new features or fixes in the current changes
4. **Commit version file**: Include version.json in your commit
5. **Push changes**: The Docker image will include the correct version information

This ensures that deployed containers always show the correct commit hash in the sidebar, making it easy to identify which code version is running.

#### Quick Version Update Script
For convenience, use the automated script:

```bash
# Run the version update script
./scripts/update_version.sh

# Commit the updated version file
git add version.json
git commit -m "Update version metadata with current commit information"

# Push changes
git push origin dev
```

**Best Practice**: Run `./scripts/update_version.sh` before any significant commit to ensure version metadata is always current.

## Project Management

### MVidarr Roadmap
- **Project Board**: https://github.com/users/prefect421/projects/1
- All development should be guided by the MVidarr Roadmap project board
- Issues should be prioritized and planned according to their position on the roadmap

### Issue Management
All issues should be planned with the following attributes:
- **Milestone**: Correlates to version number being released
- **Release Slot**: Designated release window for the issue
- **Start Date**: When work on the issue should begin
- **Stop Date**: Target completion date for the issue

### Release Management
- **Current Release**: Version 0.9.8
- **Versioning**: Milestones correlate directly to version numbers
- Releases are now utilized for version management and deployment

## Security Implementation

### Comprehensive Security Audit - Phase I Complete ✅
- **Date Completed**: July 28, 2025
- **Total Vulnerabilities Fixed**: 17 (1 Critical, 2 High, 12 Medium, 2 Low)
- **Security Documentation**: See `SECURITY_AUDIT.md` for complete details

### Critical Security Fixes Applied
- **PyMySQL 1.1.0 → 1.1.1**: Fixed SQL injection vulnerability (CVE-2024-36039)
- **Gunicorn 21.2.0 → 23.0.0**: Fixed HTTP request smuggling (CVE-2024-1135, CVE-2024-6827)
- **Pillow 10.1.0 → 10.3.0**: Fixed buffer overflow vulnerability (CVE-2024-28219)
- **Requests, urllib3, Werkzeug**: Updated to latest secure versions
- **All Dependencies**: Comprehensive security-focused updates in requirements-prod.txt (production) and requirements-dev.txt (development)

### Automated Security Monitoring Infrastructure
- **Security Scan Workflow**: `.github/workflows/security-scan.yml`
  - Daily automated security audits (2 AM UTC)
  - Multi-tool security scanning (pip-audit, safety, bandit, semgrep, trivy)
  - SARIF integration with GitHub Security tab
  - 90-day artifact retention for security reports

- **Enhanced CI/CD Security**: 
  - Security checks required for all merges to main branch
  - Real-time vulnerability detection on dependency changes
  - Branch protection with security enforcement
  - Automated GitHub issue creation for critical findings

### Security Tools & Monitoring
- **pip-audit**: Python dependency vulnerability scanning
- **Safety**: Known security vulnerability database checking
- **Bandit**: Static analysis for common Python security issues  
- **Semgrep**: Advanced security pattern matching (OWASP Top 10)
- **Trivy**: Filesystem and container vulnerability scanning
- **GitHub Security Tab**: Centralized vulnerability tracking and SARIF reporting

### Security Workflow Commands
```bash
# Run local security audit (matches CI environment)
pip-audit --requirement=requirements.txt --desc
safety check --requirement=requirements.txt
bandit -r src/ -f json
semgrep --config=p/security-audit src/
```

### Security Issue Management
- All security vulnerabilities tracked via GitHub Issues with `security` label
- Automated vulnerability assessment and prioritization
- Systematic resolution tracking and verification
- Security-focused branch protection and review requirements

## Advanced Security Implementation - Phases II & III ✅ COMPLETE

### Phase II: Advanced Security Hardening ✅

#### Enhanced Container Security
- **Workflow**: `.github/workflows/security-scan.yml` (enhanced)
- **Multi-layer Scanning**: OS vulnerabilities, library scanning, secret detection in containers
- **Configuration Analysis**: Docker security misconfigurations detection  
- **Build Integration**: Automated container security validation in CI/CD

#### Advanced Secret Management
- **Workflow**: `.github/workflows/secret-scan.yml`
- **Tools**: GitLeaks, detect-secrets, TruffleHog3 for comprehensive secret detection
- **Coverage**: Real-time detection, historical git analysis, environment variable security
- **Remediation**: Automated secret rotation recommendations and security guidance

#### Authentication & Authorization Security Auditing
- **Workflow**: `.github/workflows/auth-security.yml`
- **JWT Security**: Token validation, algorithm verification, expiration handling analysis
- **Password Security**: Hashing implementation validation, hardcoded password detection
- **Session Security**: Cookie security, session fixation protection verification
- **OAuth Security**: State parameter validation, PKCE implementation, redirect URI security

#### Security Policy Enforcement
- **Workflow**: `.github/workflows/security-policy-enforcement.yml`
- **Real-time Validation**: Code security, dependency security, container security policies
- **PR Integration**: Automated policy violation detection with blocking capabilities
- **Enforcement Levels**: Warning and blocking modes based on violation severity

### Phase III: Security Operations ✅

#### Automated Incident Response
- **Workflow**: `.github/workflows/incident-response.yml`
- **Multi-tier Response**: Critical, high, medium, low severity incident handling
- **Automated Triage**: Incident classification and appropriate response determination
- **Containment**: Immediate threat containment measures for different incident types
- **Recovery Planning**: Systematic incident recovery and validation procedures

#### Compliance Monitoring
- **Workflow**: `.github/workflows/compliance-monitoring.yml`
- **OWASP Top 10 Assessment**: Automated compliance checking for web application security
- **CIS Controls Validation**: Hardware/software inventory, data protection, access control compliance
- **NIST Cybersecurity Framework**: 5-function framework assessment (Identify, Protect, Detect, Respond, Recover)
- **Weekly Reporting**: Automated compliance status reports with improvement recommendations

### Complete Security Workflow Portfolio

#### Daily Automated Security Operations
```bash
# Complete security audit workflow execution
# All workflows run automatically on schedules:

# Daily (2 AM UTC): Comprehensive security scanning
.github/workflows/security-scan.yml

# Daily (3 AM UTC): Secret detection and management  
.github/workflows/secret-scan.yml

# Daily (5 AM UTC): Security policy enforcement
.github/workflows/security-policy-enforcement.yml

# Weekly (Sunday 4 AM UTC): Authentication security audit
.github/workflows/auth-security.yml

# Weekly (Monday 6 AM UTC): Compliance monitoring
.github/workflows/compliance-monitoring.yml

# On-demand: Incident response (triggered by security events)
.github/workflows/incident-response.yml
```

#### Security Command Reference
```bash
# Local security validation (matches CI environment)
# Phase I tools:
pip-audit --requirement=requirements.txt --desc
safety check --requirement=requirements.txt  
bandit -r src/ -f json
semgrep --config=p/security-audit src/

# Phase II tools:
gitleaks detect --source . --verbose
detect-secrets scan --all-files
semgrep --config=p/owasp-top-ten src/

# Phase III compliance:
semgrep --config=p/security-audit --config=p/secrets --config=p/owasp-top-ten src/
```

### Security Infrastructure Status: Enterprise-Grade ✅

**Comprehensive Coverage:**
- ✅ **8 Automated Security Workflows** covering all attack vectors
- ✅ **Zero Known Vulnerabilities** - All 17 original issues resolved  
- ✅ **Multi-Framework Compliance** - OWASP, CIS, NIST alignment
- ✅ **Automated Incident Response** - Multi-tier threat response capability
- ✅ **Policy Enforcement** - Real-time security policy validation
- ✅ **Enterprise Security Operations** - Continuous monitoring and assessment

**Security Posture:** MVidarr now exceeds industry security standards with enterprise-level automated security operations, continuous compliance monitoring, and comprehensive threat detection and response capabilities.

## GitHub Pages Management

### Automatic Updates
- **Trigger**: Any push to main branch affecting documentation files
- **Files Monitored**: `docs/**`, `*.md`, `_config.yml`, Jekyll pages, workflow files
- **Deployment**: Automatic Jekyll build and deploy via GitHub Actions
- **Theme**: Minima Jekyll theme with responsive design
- **URL**: https://prefect421.github.io/mvidarr

### Content Management
- **Site Structure**: Jekyll-based with navigation pages (about, installation, features, documentation, releases)  
- **Documentation Sync**: Automatically includes updated documentation from main branch
- **Version Info**: Displays current release version and roadmap information
- **Repository Links**: All documentation links reference GitHub repository content

### Maintenance Tasks
- Update version information in pages when new releases are published
- Ensure documentation links remain current with repository structure
- Monitor Pages deployment status and resolve any build failures
- Keep release information and roadmap current with project development
- keep documentation current
