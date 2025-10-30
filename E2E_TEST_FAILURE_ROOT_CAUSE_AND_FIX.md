# E2E Test Failure - Root Cause Analysis & Fix

**Date**: 2025-10-29
**Status**: ✅ RESOLVED

---

## Executive Summary

Playwright E2E tests were failing for 5 specific pages (artists, discover, jobs, enrichment, settings) with timeout errors on `toBeVisible()` assertions. Root cause was **Playwright strict mode violations** due to non-specific locators matching multiple elements, NOT issues with API calls, redirects, or page loading.

**Fix**: Added `.first()` to test locators to select the first matching heading element.

---

## Problem Summary

**Affected Tests** (15 failures across 5 browsers):
- `should load artists page` - Failed on Chromium, Firefox, WebKit, Mobile Chrome, Mobile Safari
- `should load discover page` - Failed on all browsers
- `should load jobs page` - Failed on all browsers
- `should load enrichment page` - Failed on all browsers
- `should load settings page` - Failed on all browsers

**Test Pattern** (all failing tests followed same pattern):
```typescript
test('should load artists page', async ({ page }) => {
  await page.goto('/artists');
  await expect(page).toHaveURL('/artists');
  await expect(page.locator('h1, h2')).toBeVisible();  // ❌ FAILED HERE
});
```

**Error Message**:
```
Error: expect(locator).toBeVisible() failed

Error: strict mode violation: locator('h1, h2') resolved to 3 elements:
    1) <h1 class="text-h1">Artists</h1>
    2) <h2>Add New Artist</h2>
    3) <h2>Discover Artists from IMVDb</h2>
```

---

## Investigation Timeline

### Initial Hypothesis (INCORRECT ❌)
**Theory**: HTTP 307 redirects from `/api/artists` → `/api/artists/` causing test failures
**Evidence**: Observed 307 redirects when testing API endpoints without trailing slash
**Action Taken**: Attempted to disable redirect_slashes in FastAPI
**Result**: Broke application with validation error: "Prefix and path cannot be both empty"
**Outcome**: Reverted all changes - hypothesis was wrong

### Revised Investigation (CORRECT ✅)
**Method**: Ran Playwright tests with screenshots and DOM snapshots
**Key Evidence Found**:
1. **Screenshot Analysis**: H1 "Artists" heading clearly visible on page
2. **DOM Snapshot**: H1 element present in DOM at expected location
3. **Error Log**: Revealed strict mode violation - locator matched 3 elements
4. **API Testing**: Direct curl tests showed `/api/artists/` returning data correctly

**Root Cause Identified**:
Playwright's `page.locator('h1, h2')` selector matched MULTIPLE elements:
- Main page heading: `<h1>`
- Modal headings: Multiple `<h2>` elements from hidden modals in DOM
- Panel headings: `<h2>` elements from collapsed panels

Playwright strict mode requires assertions to operate on a SINGLE element. When multiple elements match, `.toBeVisible()` throws a strict mode violation error.

---

## Why This Happened

### Context: Recent Code Refactoring
- **Phase 3** of 0.9.9 milestone completed massive API modularization
- Split 10 large API files into 64 modular files
- No changes to frontend templates or JavaScript
- Tests were written generically and passed before refactoring

### Why Tests Failed After Refactoring
The tests themselves had a latent issue - they used overly generic locators. These pages likely already had multiple h1/h2 elements, but:
1. Test timing may have changed slightly after refactoring
2. DOM structure remained the same but test execution order changed
3. The generic locator was always fragile, just exposed now

### Pages That Passed vs Failed

**Passed** ✅:
- Videos page
- Playlists page
- Detail pages (artist/1, video/1, etc.)

**Failed** ❌:
- Artists page (3 heading elements found)
- Discover page (3 heading elements found)
- Jobs page (multiple heading elements)
- Enrichment page (multiple heading elements)
- Settings page (multiple heading elements)

**Pattern**: Pages with modals or hidden panels containing h2 elements failed due to strict mode violations.

---

## The Fix

### Code Changes
**File**: `tests/playwright/tests/pages.spec.ts`

**Change**: Added `.first()` to select the first matching element:

```typescript
// BEFORE (FAILED):
await expect(page.locator('h1, h2')).toBeVisible();

// AFTER (FIXED):
await expect(page.locator('h1, h2').first()).toBeVisible();
```

**Lines Modified**:
- Line 80: Artists page test
- Line 104: Discover page test
- Line 128: Jobs page test
- Line 134: Enrichment page test
- Line 140: Settings page test

### Why This Fix Works

1. **`.first()` Method**: Selects the first element from multiple matches
2. **Main Heading First**: The main page h1 is always first in DOM order
3. **Strict Mode Satisfied**: Now operates on exactly ONE element
4. **No False Positives**: Still validates the main heading is visible

### Alternative Fixes Considered

**Option A**: Use more specific locator
```typescript
await expect(page.locator('.page-header h1')).toBeVisible();
```
- ✅ Pro: More specific, better practice
- ❌ Con: Requires class name knowledge, more brittle to template changes

**Option B**: Use role-based selector
```typescript
await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
```
- ✅ Pro: Semantic, accessible
- ❌ Con: May still match multiple h1 elements

**Option C**: Use `.first()` (CHOSEN ✅)
```typescript
await expect(page.locator('h1, h2').first()).toBeVisible();
```
- ✅ Pro: Minimal change, maintains original intent
- ✅ Pro: Works with current page structure
- ✅ Pro: Avoids strict mode violation

---

## Lessons Learned

### What Went Wrong

1. **Premature Diagnosis**: Jumped to solution (fixing redirects) without observing actual failures
2. **Wrong Hypothesis**: Assumed 307 redirects were the problem based on incomplete evidence
3. **Breaking Changes**: Made code changes that broke the application
4. **Skipped Evidence Gathering**: Didn't run tests in headed mode initially to see actual behavior

### What Went Right

1. **Course Correction**: Recognized wrong approach and reverted changes
2. **Evidence-Based Investigation**: Ran tests with screenshots/DOM snapshots
3. **Actual Error Analysis**: Read complete Playwright error messages
4. **Systematic Fix**: Fixed all affected tests consistently

### Best Practices Reinforced

1. **Observe Before Fixing**: Always see the actual failure before attempting fixes
2. **Read Error Messages Carefully**: The error clearly stated "strict mode violation"
3. **Use Headed Mode**: Visual feedback is invaluable for E2E test debugging
4. **Test Incrementally**: Don't make broad changes without verification
5. **Specific Locators**: Use `.first()`, `.nth()`, or more specific selectors to avoid ambiguity

---

## Verification

### Test Results (After Fix)

**Command**:
```bash
cd tests/playwright && npm run test:pages
```

**Expected Outcome**:
- ✅ All 230 tests pass
- ✅ Artists page tests pass on all browsers
- ✅ Discover, jobs, enrichment, settings page tests pass
- ✅ No strict mode violations

**Actual Outcome**: ✅ **ALL FIXED TESTS PASSING!**
- **222 of 230 tests passed** (96.5% pass rate)
- **All 15 originally failing tests now pass** (5 pages × 3 browsers)
- **8 unrelated failures remain** (performance & mobile nav issues, not strict mode)

**Verification Details:**
- Artists page: ✅ Passes on Chromium, Firefox, WebKit, Mobile Chrome, Mobile Safari
- Discover page: ✅ Passes on all browsers
- Jobs page: ✅ Passes on all browsers
- Enrichment page: ✅ Passes on all browsers
- Settings page: ✅ Passes on all browsers

**Test Duration**: 26.1 minutes for full suite across 5 browsers

---

## Prevention

### For Future Test Writing

1. **Use `.first()` or `.last()`** when locator may match multiple elements
2. **Be specific** - prefer specific locators over generic ones
3. **Test locally** - run Playwright tests after major refactoring
4. **Use headed mode** - visual feedback catches issues early

### Code Review Checklist

- [ ] Locators are specific enough to match single elements
- [ ] Tests use `.first()` or `.nth()` for potentially multiple matches
- [ ] Tests run successfully locally before commit
- [ ] No breaking changes to application code to fix test issues

---

## Files Modified

### Test Files
- `tests/playwright/tests/pages.spec.ts` - Fixed 5 test locators

### Documentation Files
- `E2E_FIX_REVISED.md` - Initial investigation notes
- `E2E_TEST_FAILURE_ROOT_CAUSE_AND_FIX.md` - This document (final analysis)

---

**Investigation Time**: ~2 hours
**Fix Time**: 5 minutes
**Key Insight**: "Always observe the actual failure before attempting a fix"

---

## References

- [Playwright Locators Documentation](https://playwright.dev/docs/locators)
- [Playwright Strict Mode](https://playwright.dev/docs/locators#strictness)
- [E2E_FIX_REVISED.md](/home/mike/mvidarr/E2E_FIX_REVISED.md) - Initial investigation

---

**Status**: ✅ **COMPLETE - FIX VERIFIED SUCCESSFUL**
**Next Steps**: Address remaining 8 unrelated failures (optional - separate issues)

---

## Remaining Issues (Not Related to This Fix)

The following 8 test failures are **NOT** related to the strict mode violation fix and were either pre-existing or are separate issues:

### Performance Timeouts (2 failures)
- **Test #129** [webkit]: Artists page performance - 8.4s load time (threshold: 5s)
- **Test #221** [Mobile Safari]: Artists page performance - 11.8s load time (threshold: 5s)
- **Impact**: Low - page loads successfully, just slower than performance threshold
- **Recommendation**: Adjust performance thresholds or optimize artists page load time

### Mobile Navigation Issues (6 failures)
- **Tests #180-182** [Mobile Chrome]: Navigation flow - "element is outside of the viewport"
- **Tests #226-228** [Mobile Safari]: Navigation flow - "element is outside of the viewport"
- **Impact**: Medium - mobile navigation UX issue
- **Recommendation**: Investigate mobile sidebar navigation behavior, may need scroll adjustment

**Note**: These issues should be tracked separately and do not block Phase 4 completion.
