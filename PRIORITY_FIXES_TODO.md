# High Priority Broken Links - TODO List

**Generated from comprehensive template link testing**  
**Priority: Fix critical 404s and 500s that break core functionality**

## 🔥 CRITICAL FIXES (Server Errors - Fix First)

### 1. ❌ Fix /api/playlists/ - Returns 500
- **Status:** HTTP 500 (Server Error)
- **Templates:** playlists.html, artist_detail.html, mvtv.html
- **Impact:** Core playlists functionality broken
- **Priority:** CRITICAL
- **Action:** Fix server error in playlists.py

### 2. ❌ Fix /api/auth/health - Returns 503  
- **Status:** HTTP 503 (Service Unavailable)
- **Templates:** admin/dashboard.html
- **Impact:** Admin dashboard health check broken
- **Priority:** CRITICAL
- **Action:** Fix auth health endpoint

## 🎯 HIGH IMPACT FIXES (Core Features - 404s)

### 3. ❌ Fix /api/genres - Returns 404
- **Status:** HTTP 404
- **Templates:** videos-notworking.html, videos.html, artists.html, mvtv.html
- **Impact:** Genre filtering completely broken across multiple pages
- **Priority:** HIGH
- **Action:** Implement genres API endpoint

### 4. ❌ Fix /api/videos/bulk/edit - Returns 404
- **Status:** HTTP 404
- **Templates:** videos-notworking.html, videos.html
- **Impact:** Bulk video editing broken
- **Priority:** HIGH
- **Action:** Implement bulk video edit endpoint

### 5. ❌ Fix /api/videos/bulk/organize - Returns 404
- **Status:** HTTP 404
- **Templates:** videos-notworking.html, videos.html
- **Impact:** Bulk video organization broken
- **Priority:** HIGH
- **Action:** Implement bulk video organize endpoint

### 6. ❌ Fix /api/videos/bulk/refresh-metadata - Returns 404
- **Status:** HTTP 404
- **Templates:** videos-notworking.html
- **Impact:** Bulk metadata refresh broken
- **Priority:** HIGH
- **Action:** Implement bulk metadata refresh endpoint

## 🔧 MEDIUM IMPACT FIXES (Integration Features)

### 7. ❌ Fix /api/spotify/playlists - Returns 404
- **Status:** HTTP 404
- **Templates:** spotify.html, artist_detail.html
- **Impact:** Spotify playlist integration broken
- **Priority:** MEDIUM
- **Action:** Implement Spotify playlists endpoint

### 8. ❌ Fix /api/lastfm/status - Returns 404
- **Status:** HTTP 404
- **Templates:** lastfm.html, settings.html
- **Impact:** Last.fm integration status broken
- **Priority:** MEDIUM
- **Action:** Implement Last.fm status endpoint

### 9. ❌ Fix /api/metube/queue/clear-completed - Returns 404
- **Status:** HTTP 404
- **Templates:** artist_detail.html
- **Impact:** MeTube queue management broken
- **Priority:** MEDIUM
- **Action:** Implement MeTube queue clear endpoint

### 10. ❌ Fix /api/jobs/status - Returns 404
- **Status:** HTTP 404
- **Templates:** jobs.html
- **Impact:** Job status monitoring broken
- **Priority:** MEDIUM
- **Action:** Implement jobs status endpoint

## 📝 QUICK WINS (Template Issues)

### 11. ❌ Fix template variable endpoints
- **Examples:** /title, /name, /id, /playlist, etc.
- **Status:** HTTP 404 (these are template variables, not endpoints)
- **Impact:** Template rendering issues
- **Priority:** LOW
- **Action:** Fix template syntax to properly handle variables

### 12. ❌ Fix static file paths
- **Example:** /css/placeholder-artist.png → should be /static/placeholder-artist.png
- **Status:** HTTP 404
- **Impact:** Missing images/styles
- **Priority:** LOW
- **Action:** Update template static file paths

## 🎯 NEXT STEPS

1. **Start with Critical Fixes** (500 errors) - These break existing functionality
2. **Implement High Impact Fixes** - Core features like genres and bulk operations
3. **Add Integration Features** - Spotify, Last.fm, MeTube endpoints
4. **Clean up Templates** - Fix variable handling and static paths

## 📊 PROGRESS TRACKING

- [ ] **Critical:** Fix /api/playlists/ (500 error)
- [ ] **Critical:** Fix /api/auth/health (503 error)
- [ ] **High:** Implement /api/genres endpoint
- [ ] **High:** Implement /api/videos/bulk/edit endpoint
- [ ] **High:** Implement /api/videos/bulk/organize endpoint
- [ ] **High:** Implement /api/videos/bulk/refresh-metadata endpoint
- [ ] **Medium:** Implement Spotify endpoints
- [ ] **Medium:** Implement Last.fm endpoints
- [ ] **Medium:** Implement MeTube endpoints
- [ ] **Medium:** Implement jobs endpoints
- [ ] **Low:** Fix template variable issues
- [ ] **Low:** Fix static file paths

**Target:** Increase link success rate from 16.9% to 80%+ by fixing top 20 issues