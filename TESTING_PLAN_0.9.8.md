# MVidarr 0.9.8 User Testing Plan

## 🎯 Testing Objectives
- Validate complete subtitle system functionality
- Verify video quality improvements 
- Test FastAPI migration stability
- Identify any regression issues
- Document performance baseline for 0.9.9 optimization

## 🧪 Critical Test Areas

### 1. Subtitle System Testing
**Priority: HIGH**

#### Test Cases:
- [ ] **Download with Subtitles**: Add new video with subtitles enabled
- [ ] **Popup Player Subtitles**: Test subtitle display in video cards popup
- [ ] **Detail Page Subtitles**: Verify subtitles in video detail page
- [ ] **Language Resolution**: Test `en.*` pattern matching
- [ ] **Multiple Formats**: Test VTT, SRT, ASS subtitle files
- [ ] **Settings Respect**: Verify global subtitle settings are honored

#### Expected Results:
- Subtitles automatically download for new videos
- CC controls visible in all video players
- Multiple language options available
- First subtitle track auto-enabled

### 2. Video Quality & Download Testing
**Priority: HIGH**

#### Test Cases:
- [ ] **Quality Selection**: Download videos at 1080p, 720p, 480p
- [ ] **Format Verification**: Confirm separate video+audio prioritization
- [ ] **Session Stability**: Test bulk operations without session errors
- [ ] **Download Progress**: Monitor download queue functionality
- [ ] **Error Handling**: Test failed download recovery

#### Expected Results:
- Videos download at requested quality (not 360p)
- No SQLAlchemy session binding errors
- Stable bulk operations
- Clear error reporting

### 3. Core Functionality Testing
**Priority: MEDIUM**

#### Test Cases:
- [ ] **Video Addition**: YouTube URL import
- [ ] **Metadata Enrichment**: Enhanced metadata processing
- [ ] **Search & Filter**: Video discovery and filtering
- [ ] **Artist Management**: Artist operations and bulk actions
- [ ] **Playlist Operations**: Playlist creation and management
- [ ] **System Settings**: Configuration changes and persistence

### 4. Performance & Stability Testing
**Priority: MEDIUM**

#### Test Cases:
- [ ] **Memory Usage**: Monitor memory consumption over time
- [ ] **Response Times**: API endpoint performance
- [ ] **Concurrent Users**: Multiple user sessions
- [ ] **Large Collections**: Performance with 500+ videos
- [ ] **Background Jobs**: Long-running task stability

## 🐛 Issue Tracking

### Issue Template:
```
**Issue Type**: [Bug/Performance/UI/Feature]
**Severity**: [Critical/High/Medium/Low]
**Component**: [Subtitles/Download/UI/API/etc.]
**Description**: Clear description of the issue
**Steps to Reproduce**: 
1. Step one
2. Step two
3. Expected vs Actual behavior
**Environment**: Browser, OS, etc.
**Screenshots**: If applicable
```

### Priority Levels:
- **Critical**: System crashes, data loss, security issues
- **High**: Core functionality broken, user blocking issues
- **Medium**: Usability issues, performance problems
- **Low**: Cosmetic issues, minor improvements

## 📊 Testing Metrics

### Performance Baseline (Pre-0.9.9):
- [ ] Memory usage at startup: _____ MB
- [ ] Memory usage after 1 hour: _____ MB
- [ ] Average API response time: _____ ms
- [ ] Video download time (5min video): _____ seconds
- [ ] Metadata enrichment time: _____ seconds

### Functionality Checklist:
- [ ] All critical features working
- [ ] No regression from previous version
- [ ] New subtitle features functional
- [ ] Quality improvements verified
- [ ] No session binding errors

## 🎯 Success Criteria for 0.9.8

### Must Have (Release Blockers):
- ✅ Subtitle system fully functional
- ✅ Video quality improvements working
- ✅ No SQLAlchemy session errors
- ✅ Core video operations stable
- ✅ FastAPI migration complete

### Should Have:
- [ ] Performance within acceptable limits
- [ ] All major features working correctly
- [ ] Good user experience across features
- [ ] Comprehensive error handling

### Nice to Have:
- [ ] Optimized performance
- [ ] Enhanced UI/UX
- [ ] Additional feature polish

## 📝 Testing Log

### Date: ___________
**Tester**: ___________
**Version**: 0.9.8
**Test Duration**: ___________

#### Issues Found:
1. **Issue ID**: #___
   **Severity**: ___
   **Description**: ___
   **Status**: [Open/Fixed/Deferred]

#### Performance Notes:
- Memory usage: ___
- Response times: ___
- Any notable observations: ___

#### Recommendations:
- Priority fixes for 0.9.8: ___
- Items to defer to 0.9.9: ___
- Optimization opportunities: ___

## 🚀 Post-Testing Actions

### If Critical Issues Found:
1. Create GitHub issues with high priority
2. Fix immediately before 0.9.9 planning
3. Re-test affected areas
4. Update documentation

### If Minor Issues Found:
1. Document in GitHub issues
2. Prioritize for 0.9.9 or later
3. Consider if they block public release

### If Performance Issues Found:
1. Profile and identify bottlenecks
2. Add to 0.9.9 optimization targets
3. Set performance goals for next release

---

**Testing Status**: 🟡 Ready to Begin
**Next Phase**: 0.9.9 Code Cleanup & Optimization Planning