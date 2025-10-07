# MVidarr 0.9.8 User Testing Issues

## 🚨 **CRITICAL ISSUES** (Release Blockers)

### Dashboard Issues
- [ ] **#UT-001** Artist add via search shows "Artist undefined added successfully!" 
  - **API**: POST `/api/artists/import-from-imvdb` returns 502 Bad Gateway
  - **Impact**: Cannot add artists via search functionality
  - **Priority**: CRITICAL

- [ ] **#UT-002** Manual artist addition requires IMVDb ID
  - **API**: POST `/api/artists/` returns 422 Unprocessable Entity without IMVDb ID
  - **Impact**: User cannot manually add artists without external ID
  - **Priority**: HIGH

- [ ] **#UT-003** Logout redirects to non-existent `/simple-login` page
  - **Impact**: Users cannot properly log out
  - **Priority**: CRITICAL

### Videos Page Issues
- [ ] **#UT-004** Search functionality completely broken
  - **API**: GET `/api/search/suggestions` returns 500 Internal Server Error
  - **Impact**: Users cannot search for videos
  - **Priority**: CRITICAL

- [ ] **#UT-005** Video deletion fails
  - **API**: DELETE `/api/videos/423` returns 500 Internal Server Error
  - **Impact**: Users cannot delete videos
  - **Priority**: CRITICAL

- [ ] **#UT-006** Bulk operations broken - missing error handlers
  - **Error**: `showSuccessMessage is not defined`, `showErrorMessage is not defined`
  - **Impact**: All bulk operations fail with JavaScript errors
  - **Priority**: CRITICAL

### Playlists Completely Broken
- [ ] **#UT-007** Playlist page fails to load
  - **API**: Failed to load playlists completely
  - **Impact**: Entire playlist functionality non-functional
  - **Priority**: CRITICAL

- [ ] **#UT-008** Create playlist fails
  - **API**: POST `/api/playlists/` returns 500 Internal Server Error
  - **Impact**: Cannot create new playlists
  - **Priority**: CRITICAL

## 🔴 **HIGH PRIORITY ISSUES**

### Artist Management
- [ ] **#UT-009** Scan missing thumbnails fails
  - **API**: POST `/api/artists/scan-missing-thumbnails` returns 405 Method Not Allowed
  - **Priority**: HIGH

- [ ] **#UT-010** All bulk artist operations fail
  - **API**: POST `/api/artists/bulk-edit` returns 405 Method Not Allowed
  - **Impact**: Bulk artist management non-functional
  - **Priority**: HIGH

### Video Operations
- [ ] **#UT-011** Video quality still downloading at 360p
  - **Issue**: Bulk download operations not using enhanced quality settings
  - **Impact**: Poor video quality despite fixes
  - **Priority**: HIGH

- [ ] **#UT-012** Enhanced metadata refresh hangs
  - **Behavior**: "Enriching metadata..." message never disappears
  - **Impact**: User cannot tell if operation completed
  - **Priority**: HIGH

- [ ] **#UT-013** Download retry functionality broken
  - **API**: POST `/api/metube/download/1/retry` returns 400 Bad Request
  - **Priority**: HIGH

### Settings Issues
- [ ] **#UT-014** Service connections failing
  - **APIs**: IMVDb test returns 503, Spotify test returns undefined
  - **Impact**: Cannot verify service integrations
  - **Priority**: HIGH

- [ ] **#UT-015** Blacklist functionality broken
  - **API**: GET `/api/videos/blacklist` returns 422 Unprocessable Entity
  - **Impact**: Cannot manage video blacklist
  - **Priority**: HIGH

## 🟡 **MEDIUM PRIORITY ISSUES**

### UI/UX Issues
- [ ] **#UT-016** Download progress bars not functional
  - **Behavior**: Progress bars show no progress
  - **Resolution**: Fix or remove non-functional elements
  - **Priority**: MEDIUM

- [ ] **#UT-017** Missing pagination on videos page
  - **Impact**: Performance issues with large collections
  - **Priority**: MEDIUM

- [ ] **#UT-018** Thumbnail generation sticks on "Starting"
  - **Behavior**: UI shows "Starting" but never progresses
  - **Priority**: MEDIUM

### MvTV Issues
- [ ] **#UT-019** Song information not updating with video changes
  - **Behavior**: Metadata below video doesn't sync with video controls
  - **Priority**: MEDIUM

### Background Jobs
- [ ] **#UT-020** System status always shows "Deprecated"
  - **Priority**: MEDIUM

- [ ] **#UT-021** Job counts inaccurate
  - **Priority**: MEDIUM

- [ ] **#UT-022** Move background jobs to settings tab
  - **UX**: Remove from main navigation
  - **Priority**: LOW

### Settings Cleanup
- [ ] **#UT-023** Outdated links and buttons in System tab
  - **Impact**: Links point to non-existent pages
  - **Priority**: MEDIUM

- [ ] **#UT-024** YouTube OAuth2 section relevance
  - **Question**: Is this still needed or should be removed?
  - **Priority**: LOW

## 📊 **ISSUE BREAKDOWN BY SEVERITY**

| **Severity** | **Count** | **Percentage** |
|--------------|-----------|----------------|
| **CRITICAL** | 8 | 33% |
| **HIGH** | 8 | 33% |
| **MEDIUM** | 6 | 25% |
| **LOW** | 2 | 9% |
| **TOTAL** | 24 | 100% |

## 🎯 **IMMEDIATE ACTION REQUIRED**

### Before 0.9.9 Cleanup:
1. **Fix Critical API Endpoints** (8 issues)
   - Artist import functionality
   - Search functionality  
   - Video deletion
   - Playlist operations
   - Logout functionality

2. **JavaScript Error Handling** (Multiple issues)
   - Missing `showSuccessMessage` and `showErrorMessage` functions
   - Bulk operation error handling

3. **API Method Mismatches** (Multiple issues)
   - 405 Method Not Allowed errors indicate routing issues
   - 422 Unprocessable Entity suggests validation problems

### Testing Validation:
- [ ] **All CRITICAL issues** must be resolved before proceeding to 0.9.9
- [ ] **HIGH priority issues** should be addressed for public release
- [ ] **MEDIUM/LOW issues** can be deferred to future releases

## 📋 **TESTING NOTES**

### What Works:
- ✅ Basic video playback
- ✅ Subtitle system (needs verification)
- ✅ Manual artist addition (with IMVDb ID)
- ✅ Core navigation

### What's Broken:
- ❌ Search functionality
- ❌ Artist management
- ❌ Playlist system
- ❌ Bulk operations
- ❌ Service integrations

### Root Causes Identified:
1. **API Routing Issues**: Multiple 405 Method Not Allowed errors
2. **JavaScript Dependencies**: Missing error handling functions
3. **Validation Errors**: 422 errors suggest API validation problems
4. **Service Integration**: External service connections failing

## 🚀 **NEXT STEPS**

1. **Immediate Fixes**: Address all CRITICAL issues before any 0.9.9 work
2. **API Audit**: Review all failing endpoints for routing and validation
3. **JavaScript Cleanup**: Fix missing function definitions
4. **Re-test**: Full regression testing after fixes
5. **0.9.9 Planning**: Proceed with cleanup only after stable 0.9.8

---

**Testing Date**: September 26, 2025  
**Tester**: User Testing Session  
**Version**: 0.9.8  
**Status**: 🔴 MAJOR ISSUES FOUND - REQUIRES IMMEDIATE ATTENTION