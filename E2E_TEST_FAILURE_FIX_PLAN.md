# E2E Test Failure Fix Plan
## Root Cause Analysis & Resolution Strategy

**Date**: 2025-10-29
**Issue**: Playwright E2E tests failing (34+ failures)
**Status**: Root cause identified
**Priority**: CRITICAL (Blocks 1.0.0 release)

---

## Root Cause Identified ✅

###  Main Issue: API Route Trailing Slash Redirects

**Problem**: FastAPI is issuing 307 Temporary Redirects for API endpoints due to trailing slash mismatch.

**Evidence**:
```bash
# API calls without trailing slashes return 307 redirects
curl -I http://localhost:5000/api/artists
→ HTTP/1.1 307 Temporary Redirect
→ Location: http://localhost:5000/api/artists/

curl http://localhost:5000/api/artists/
→ HTTP/1.1 200 OK (works correctly)
```

**Route Configuration**:
```python
# In src/api/fastapi/artists.py
router = APIRouter(
    prefix="/api/artists",  # No trailing slash
    tags=["artists"],
)

# In src/api/fastapi/artists_crud.py
@router.get("/", response_model=Dict[str, Any])  # Creates /api/artists/ WITH slash
```

**Impact on Tests**:
1. **Page Loading Stuck**: Frontend JavaScript makes API calls like `/api/artists` (no slash)
2. **307 Redirect**: FastAPI redirects to `/api/artists/` (with slash)
3. **Authentication Loss**: Redirects may not preserve authentication cookies properly
4. **Timeout**: Playwright tests timeout waiting for h1/h2 elements (15s actionTimeout)
5. **Test Failure**: Page shows "Loading artists..." indefinitely

---

## Why This Breaks E2E Tests

### Frontend Behavior
- HTML pages load successfully: `/artists` → 200 OK ✅
- JavaScript makes API call: `/api/artists` → 307 Redirect ⚠️
- Redirect to: `/api/artists/` → May lose auth or timeout ❌
- Frontend stuck: "Loading artists..." never completes ❌

### Test Expectations
```typescript
test('should load artists page', async ({ page }) => {
  await page.goto('/artists');
  await expect(page).toHaveURL('/artists');
  await expect(page.locator('h1, h2')).toBeVisible();  // FAILS: Never appears
});
```

The h1/h2 elements are rendered by JavaScript **after** the API call completes. Since the API call fails/times out, the elements never appear, and the test times out after 15 seconds.

---

## Fix Options

### Option 1: Add redirect_slashes=False (FASTEST FIX ⚡)

**Implementation**:
```python
# In fastapi_app.py or main app initialization
from fastapi import FastAPI

app = FastAPI(redirect_slashes=False)
```

**Pros**:
- ✅ Single line change
- ✅ Fixes all routes immediately
- ✅ No route definition changes needed
- ✅ Fast to implement and test

**Cons**:
- ⚠️ Routes must be called exactly as defined
- ⚠️ Frontend must use correct trailing slashes
- ⚠️ Could break existing API clients if they don't use trailing slashes

**Recommendation**: ✅ **Use this for immediate fix**

---

### Option 2: Normalize Route Definitions (BEST PRACTICE 🎯)

**Implementation**:
```python
# Option 2A: Remove trailing slashes from all list endpoints
@router.get("", response_model=Dict[str, Any])  # Instead of "/"
async def get_artists():
    ...

# Option 2B: Add trailing slashes to all route prefixes
router = APIRouter(
    prefix="/api/artists/",  # Add trailing slash
    tags=["artists"],
)
```

**Pros**:
- ✅ Follows RESTful conventions
- ✅ Consistent with FastAPI best practices
- ✅ More predictable API behavior
- ✅ Better for API documentation

**Cons**:
- ⚠️ Requires updating many route definitions
- ⚠️ More testing needed
- ⚠️ Could introduce regressions

**Recommendation**: ✅ **Implement after Option 1 stabilizes**

---

### Option 3: Update Frontend to Use Trailing Slashes (NOT RECOMMENDED ❌)

**Implementation**:
Update all frontend JavaScript API calls to include trailing slashes.

**Pros**:
- ✅ Backend routes remain unchanged

**Cons**:
- ❌ Requires updating many frontend files
- ❌ Error-prone (easy to miss some calls)
- ❌ Not a standard REST API convention
- ❌ Breaks API documentation examples

**Recommendation**: ❌ **Do not use this approach**

---

## Recommended Fix Strategy

### Phase 1: Immediate Fix (TODAY)

**Goal**: Get E2E tests passing

**Steps**:
1. **Disable trailing slash redirects in FastAPI**:
   ```python
   # In fastapi_app.py
   app = FastAPI(
       title="MVidarr API",
       version="0.9.9",
       redirect_slashes=False,  # ADD THIS LINE
   )
   ```

2. **Test the fix**:
   ```bash
   # Restart the application
   # Run Playwright tests
   cd tests/playwright
   npm test
   ```

3. **Verify API endpoints**:
   ```bash
   curl http://localhost:5000/api/artists  # Should return 200, not 307
   curl http://localhost:5000/api/videos   # Should return 200, not 307
   ```

**Expected Results**:
- ✅ API calls return 200 directly (no 307 redirects)
- ✅ Frontend loads data successfully
- ✅ E2E tests pass (122/122)

**Time Estimate**: 15 minutes

---

### Phase 2: Normalize Routes (AFTER PHASE 1)

**Goal**: Follow FastAPI best practices

**Steps**:
1. **Update route definitions** to use consistent trailing slash convention:
   ```python
   # Choose one approach and apply consistently:

   # Approach A: No trailing slashes (RESTful)
   @router.get("", response_model=Dict[str, Any])

   # Approach B: With trailing slashes (FastAPI convention)
   @router.get("/", response_model=Dict[str, Any])
   # AND update prefix
   router = APIRouter(prefix="/api/artists/", ...)
   ```

2. **Update all affected files**:
   - `src/api/fastapi/artists_crud.py`
   - `src/api/fastapi/videos_crud.py`
   - `src/api/fastapi/playlists_crud.py`
   - All other route files with list endpoints

3. **Test thoroughly**:
   - Unit tests
   - API tests
   - E2E tests
   - Manual testing

4. **Re-enable redirect_slashes** (optional):
   ```python
   app = FastAPI(
       redirect_slashes=True,  # Default behavior
   )
   ```

**Expected Results**:
- ✅ Consistent route definitions
- ✅ Predictable API behavior
- ✅ Better API documentation
- ✅ All tests still passing

**Time Estimate**: 2-3 hours

---

### Phase 3: Comprehensive Testing (AFTER PHASE 2)

**Goal**: Ensure no regressions

**Test Checklist**:
- [ ] All Playwright E2E tests passing (122/122)
- [ ] All Python unit tests passing
- [ ] All API endpoint tests passing
- [ ] Manual testing of all pages
- [ ] Manual testing of all API endpoints
- [ ] Performance benchmarks still met
- [ ] Security audit clean

---

## Files to Modify

### Phase 1: Immediate Fix
**File**: `fastapi_app.py`
**Change**: Add `redirect_slashes=False` to FastAPI() initialization

### Phase 2: Route Normalization
**Files** (if normalizing routes):
- `src/api/fastapi/artists.py` - Main router prefix
- `src/api/fastapi/artists_crud.py` - List endpoint route
- `src/api/fastapi/videos.py` - Main router prefix
- `src/api/fastapi/videos_crud.py` - List endpoint route
- `src/api/fastapi/playlists.py` - Main router prefix
- `src/api/fastapi/playlists_crud.py` - List endpoint route
- All other route files with `/` endpoints

---

## Testing Strategy

### Unit Tests
```bash
cd /home/mike/mvidarr
venv/bin/python3 -m pytest tests/test_smoke.py -v
```

### API Tests
```bash
# Test each endpoint directly
curl http://localhost:5000/api/artists
curl http://localhost:5000/api/videos
curl http://localhost:5000/api/playlists
curl http://localhost:5000/api/jobs
```

### E2E Tests
```bash
cd tests/playwright
npm test                    # All tests
npm run test:pages          # Page navigation tests only
npm run test:api            # API tests only
npm run test:auth           # Authentication tests only
```

### Manual Testing
- [ ] Visit /artists page - should load artist list
- [ ] Visit /videos page - should load video list
- [ ] Visit /playlists page - should load playlists
- [ ] Visit /discover page - should load discovery UI
- [ ] Visit /enrichment page - should load enrichment dashboard
- [ ] Visit /jobs page - should load jobs list
- [ ] Visit /settings page - should load settings

---

## Expected Outcomes

### After Phase 1 (Immediate Fix)
- **E2E Tests**: 122/122 passing (100%)
- **API Performance**: <500ms response time maintained
- **Frontend**: All pages load data successfully
- **No Breaking Changes**: Existing functionality preserved

### After Phase 2 (Route Normalization)
- **Code Quality**: Consistent route definitions
- **API Documentation**: Clear, predictable endpoints
- **Maintainability**: Easier to understand and modify
- **Best Practices**: Follows FastAPI conventions

### After Phase 3 (Comprehensive Testing)
- **Regression Free**: All systems verified working
- **Performance**: Benchmarks maintained
- **Security**: Audit findings still addressed
- **Ready for 1.0.0**: No blocking issues

---

## Rollback Plan

### If Phase 1 Causes Issues
```python
# Revert fastapi_app.py change
app = FastAPI(
    # Remove redirect_slashes=False
)
```

### If Phase 2 Causes Issues
- Git revert to commit before route changes
- Restore from backup files
- Re-run Phase 1 only

---

## Additional Considerations

### Other Potential Issues

While the trailing slash redirect is the primary issue, also verify:

1. **CORS Configuration**: Ensure redirects don't break CORS
   ```python
   # Check CORS middleware in fastapi_app.py
   app.add_middleware(
       CORSMiddleware,
       allow_credentials=True,  # Important for auth
   )
   ```

2. **Session Authentication**: Verify sessions persist through redirects
   ```python
   # Check session middleware configuration
   ```

3. **Frontend Error Handling**: Ensure graceful degradation on API failures
   ```javascript
   // Check for proper error handling in frontend JavaScript
   ```

### Example Tests (After Fix)

**Before Fix**:
```bash
$ curl -I http://localhost:5000/api/artists
HTTP/1.1 307 Temporary Redirect  # ❌ BAD
```

**After Fix**:
```bash
$ curl -I http://localhost:5000/api/artists
HTTP/1.1 200 OK  # ✅ GOOD
```

---

## Success Criteria

### Phase 1 Complete When:
- [ ] `redirect_slashes=False` added to FastAPI initialization
- [ ] Application restarted
- [ ] API endpoints return 200 directly (no 307)
- [ ] E2E tests passing (at least 90%+)
- [ ] Manual testing confirms pages load data

### Phase 2 Complete When:
- [ ] All route definitions normalized
- [ ] Code follows consistent convention
- [ ] API documentation updated
- [ ] All tests passing (100%)

### Phase 3 Complete When:
- [ ] All test suites passing (unit, API, E2E)
- [ ] Performance benchmarks met
- [ ] Security audit addressed
- [ ] Manual testing complete
- [ ] Ready for Phase 5 (Documentation)

---

## Timeline

| Phase | Duration | Dependencies | Blocker |
|-------|----------|--------------|---------|
| Phase 1 | 15 min | None | YES |
| Phase 2 | 2-3 hours | Phase 1 complete | NO |
| Phase 3 | 1-2 hours | Phase 2 complete | NO |
| **Total** | **3-5 hours** | Sequential | Phase 1 only |

---

## Notes

1. **Phase 1 is critical**: Must be completed before continuing with Phase 5 (Documentation)
2. **Phase 2 is optional**: Can be deferred to a later release if needed
3. **Phase 3 is recommended**: Ensures quality before 1.0.0 release

---

## References

- **FastAPI Trailing Slashes**: https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/#trailing-slash-handling
- **Playwright Test Results**: `/home/mike/mvidarr/tests/playwright/test-results/`
- **Phase 4 Test Report**: `/home/mike/mvidarr/PHASE_4_TEST_RESULTS.md`
- **Related Files**:
  - `fastapi_app.py` - Main application
  - `src/api/fastapi/*.py` - All router files
  - `tests/playwright/tests/pages.spec.ts` - Failing tests

---

**Report Generated**: 2025-10-29
**Last Updated**: 2025-10-29 18:15 UTC
**Status**: Ready for implementation
**Next Action**: Implement Phase 1 (add redirect_slashes=False)
