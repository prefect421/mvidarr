# Browser Compatibility Guide

## Supported Browsers

MVidarr is tested and supported on the following modern web browsers:

### ✅ Fully Supported Browsers

| Browser | Minimum Version | Status | Notes |
|---------|----------------|--------|-------|
| **Google Chrome** | 90+ | ⚠️ With workarounds | See Chrome-specific notes below |
| **Mozilla Firefox** | 88+ | ✅ Full support | Recommended for best experience |
| **Safari** | 14+ | ✅ Full support | macOS and iOS |
| **Microsoft Edge** | 90+ | ✅ Full support | Chromium-based |
| **Opera** | 76+ | ✅ Full support | Chromium-based |
| **Brave** | 1.24+ | ✅ Full support | Chromium-based |

### Minimum Requirements

- **JavaScript**: Must be enabled
- **Cookies**: Must be enabled for authentication
- **WebSocket**: Required for real-time features
- **HTML5 Video**: Required for video playback
- **CORS**: Browser must support CORS for subtitle loading

---

## Chrome-Specific Behavior

### ⚠️ Chrome STATUS_BREAKPOINT Crash Workaround

**Issue Identified**: Chrome browser (versions 90-130+) experiences STATUS_BREAKPOINT crashes when seeking videos with active subtitle tracks. This is a Chrome-specific decoder bug.

**Workaround Implemented** (v0.10.0-beta.1):
- **Behavior**: Subtitles are automatically disabled during video seek operations in Chrome only
- **Detection**: User agent check for Chrome (excluding Edge)
- **Scope**: Only affects Chrome browser - Firefox, Safari, Edge unaffected

**User Impact**:
- **Chrome Users**: Subtitles may need to be manually re-enabled after seeking
- **Trade-off**: Stability prioritized over convenience to prevent browser crashes
- **Other Browsers**: Normal subtitle behavior maintained

**Technical Details**:
```javascript
// Chrome detection and workaround
if (navigator.userAgent.indexOf('Chrome') > -1 && navigator.userAgent.indexOf('Edg') === -1) {
    videoElement.addEventListener('seeking', function() {
        // Disable all subtitle tracks during seek
        for (let i = 0; i < videoElement.textTracks.length; i++) {
            videoElement.textTracks[i].mode = 'disabled';
        }
    });
}
```

**Recommendation**: For the best subtitle experience during video seeking, consider using Firefox, Safari, or Edge browsers.

---

## Browser Feature Support Matrix

### Video Playback Features

| Feature | Chrome | Firefox | Safari | Edge | Notes |
|---------|--------|---------|--------|------|-------|
| **MP4 Playback** | ✅ | ✅ | ✅ | ✅ | All formats supported |
| **WebM Playback** | ✅ | ✅ | ⚠️ | ✅ | Safari: Limited codec support |
| **MKV Transcoding** | ✅ | ✅ | ✅ | ✅ | Real-time server-side transcoding |
| **Subtitle Support** | ⚠️ | ✅ | ✅ | ✅ | Chrome: See workaround above |
| **Timeline Scrubbing** | ⚠️ | ✅ | ✅ | ✅ | Chrome: Subtitles disabled during seek |
| **Fullscreen Mode** | ✅ | ✅ | ✅ | ✅ | All browsers |
| **Picture-in-Picture** | ✅ | ✅ | ✅ | ✅ | All browsers |
| **Keyboard Shortcuts** | ✅ | ✅ | ✅ | ✅ | All browsers |

### Subtitle Features

| Feature | Chrome | Firefox | Safari | Edge | Notes |
|---------|--------|---------|--------|------|-------|
| **WebVTT (.vtt)** | ⚠️ | ✅ | ✅ | ✅ | Chrome: Disabled during seeking |
| **SubRip (.srt)** | ⚠️ | ✅ | ✅ | ✅ | Chrome: Disabled during seeking |
| **ASS/SSA (.ass/.ssa)** | ⚠️ | ✅ | ✅ | ✅ | Chrome: Disabled during seeking |
| **Multiple Languages** | ✅ | ✅ | ✅ | ✅ | All browsers |
| **Auto-Enable** | ⚠️ | ✅ | ✅ | ✅ | Chrome: May reset after seek |
| **CC Controls** | ✅ | ✅ | ✅ | ✅ | Native browser controls |

### UI/UX Features

| Feature | Chrome | Firefox | Safari | Edge | Notes |
|---------|--------|---------|--------|------|-------|
| **Responsive Design** | ✅ | ✅ | ✅ | ✅ | All browsers |
| **Dark Mode** | ✅ | ✅ | ✅ | ✅ | All browsers |
| **Modal Popups** | ✅ | ✅ | ✅ | ✅ | All browsers |
| **Drag & Drop** | ✅ | ✅ | ✅ | ✅ | All browsers |
| **Session Management** | ✅ | ✅ | ✅ | ✅ | Cookie-based authentication |

---

## Known Browser Issues

### Chrome (All Versions)
- **Issue**: STATUS_BREAKPOINT crash when seeking with subtitles
- **Severity**: High (browser crash)
- **Workaround**: Automatic subtitle disable during seeking
- **Status**: Workaround implemented in v0.10.0-beta.1
- **Upstream Bug**: Reported to Chromium team (pending fix)

### Safari (iOS)
- **Issue**: Limited WebM codec support
- **Severity**: Low (alternative formats available)
- **Workaround**: Server automatically transcodes to MP4
- **Status**: No action required

---

## Browser Testing Recommendations

### For Best Experience
1. **Primary Recommendation**: Firefox or Edge for full subtitle support
2. **Secondary Recommendation**: Safari for macOS/iOS users
3. **Chrome Users**: Be aware of subtitle behavior during seeking

### For Developers
- Test all video features across Chrome, Firefox, and Safari
- Verify subtitle behavior in each browser
- Check responsive design on mobile browsers
- Validate authentication flow in all browsers

---

## Reporting Browser-Specific Issues

If you encounter browser-specific issues:

1. **Check Known Issues**: Review this document first
2. **Gather Information**:
   - Browser name and version
   - Operating system
   - Steps to reproduce
   - Console errors (F12 Developer Tools)
3. **Report Issue**: https://github.com/prefect421/mvidarr/issues
4. **Include**: Browser user agent string

**Get User Agent**: Open browser console (F12) and type:
```javascript
navigator.userAgent
```

---

## Version History

- **v0.10.0-beta.1** (2025-12-02): Added Chrome STATUS_BREAKPOINT workaround
- **v0.9.9** (2025-11-04): Initial browser compatibility documentation

---

## Related Documentation

- [Installation Guide](INSTALLATION-GUIDE.md)
- [User Guide](USER-GUIDE.md)
- [Troubleshooting](TROUBLESHOOTING.md)
- [API Documentation](API_DOCUMENTATION.md)
