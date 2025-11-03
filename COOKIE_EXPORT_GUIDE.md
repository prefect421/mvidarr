# YouTube Cookie Export Guide for Age-Restricted Videos

## Problem

Your current cookie file at `data/cookies/youtube_cookies.txt` does not contain the proper authentication cookies needed for age-restricted videos. This is why downloads fail with:

```
ERROR: Sign in to confirm your age. This video may be inappropriate for some users.
```

## Solution: Export Fresh Cookies

You need to export fresh cookies from a logged-in YouTube session following these **exact steps**:

### Step 1: Install Cookie Extension

Install one of these browser extensions:
- **Chrome/Edge**: [Get cookies.txt](https://chrome.google.com/webstore/detail/get-cookiestxt/bgaddhkoddajcdgocldbbfleckgcbcid)
- **Firefox**: [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/)

### Step 2: Export Cookies (Critical Steps!)

1. **Open a NEW private/incognito window** in your browser
2. **Log into YouTube** with an age-verified account
3. **Navigate to** `https://www.youtube.com/robots.txt` (must be in same private tab)
4. **Click the cookie extension icon** and select "Export" or "Export All"
5. **Save as**: `youtube_cookies.txt` (Netscape format)
6. **Immediately close** the private/incognito window

### Step 3: Upload to MVidarr

Upload the exported `youtube_cookies.txt` file to:
```
/home/mike/mvidarr/data/cookies/youtube_cookies.txt
```

Replace the existing file.

### Step 4: Verify

Test with a simple command:
```bash
/root/.local/bin/yt-dlp --cookies data/cookies/youtube_cookies.txt --skip-download "https://www.youtube.com/watch?v=anlghGgWuAs"
```

If it says "Extracting" without age-restriction errors, the cookies work!

## Why This Method?

- **Private/incognito window**: Prevents YouTube's automatic cookie rotation
- **robots.txt page**: Ensures all necessary authentication cookies are loaded
- **Immediate close**: Stops session rotation that would invalidate cookies

## Important Warnings

⚠️ **Account Risk**: Using your YouTube account with yt-dlp may result in temporary or permanent account suspension. Google discourages automated access.

⚠️ **Cookie Expiration**: Cookies typically last 1-2 weeks. You'll need to re-export them periodically.

⚠️ **Security**: Never share your cookie file! It contains full access to your YouTube account.

## Troubleshooting

**Still getting age-restriction errors?**

1. Verify your YouTube account has age verification enabled:
   - Go to https://www.youtube.com/account
   - Check that your birthdate shows you're 18+

2. Check cookie file format:
   - Should start with: `# Netscape HTTP Cookie File`
   - Should have lines starting with `.youtube.com`

3. Check cookie file is readable:
   ```bash
   ls -lh /home/mike/mvidarr/data/cookies/youtube_cookies.txt
   ```
   Should show: `-rw-r--r--` permissions

## Alternative: Non-Age-Restricted Videos

If you don't want to deal with cookies, simply avoid downloading age-restricted videos. Most music videos are NOT age-restricted.
