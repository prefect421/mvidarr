#!/usr/bin/env python3
"""
Test to verify lyrics display fix for video 170
"""

import asyncio
import sys
import os
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_lyrics_display():
    """Test that lyrics are displayed on page load"""
    
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context()
    page = await context.new_page()
    
    try:
        # Login
        await page.goto("http://192.168.1.145:5000/auth/login")
        await page.fill('#username', 'admin')
        await page.fill('#password', 'mvidarr')
        await page.click('button[type="submit"]')
        await asyncio.sleep(2)
        
        # Navigate to video 170
        print("🎵 Testing lyrics display for video 170...")
        await page.goto("http://192.168.1.145:5000/video/170")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)  # Allow time for page to fully load
        
        # Check if lyrics content is displayed
        lyrics_content = await page.text_content('#lyricsContent')
        print(f"   Lyrics content found: {'YES' if lyrics_content else 'NO'}")
        print(f"   Content preview: {lyrics_content[:100] if lyrics_content else 'None'}...")
        
        # Check if placeholder message is showing
        has_placeholder = await page.query_selector('.lyrics-placeholder')
        print(f"   Shows placeholder: {'YES' if has_placeholder else 'NO'}")
        
        # Check if actual lyrics text is showing
        lyrics_text = await page.query_selector('.lyrics-text')
        print(f"   Shows lyrics text: {'YES' if lyrics_text else 'NO'}")
        
        if lyrics_text:
            actual_lyrics = await lyrics_text.text_content()
            print(f"   Lyrics length: {len(actual_lyrics) if actual_lyrics else 0} characters")
            
            if actual_lyrics and len(actual_lyrics) > 100:
                print("✅ PASS: Lyrics are displayed correctly on page load")
                return True
            else:
                print("❌ FAIL: Lyrics text element found but content is too short")
                return False
        else:
            print("❌ FAIL: Lyrics are not displayed on page load")
            return False
            
    except Exception as e:
        print(f"❌ FAIL: Test error: {e}")
        return False
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()

if __name__ == "__main__":
    result = asyncio.run(test_lyrics_display())
    sys.exit(0 if result else 1)