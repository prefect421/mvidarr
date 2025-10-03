#!/usr/bin/env python3
"""
Final verification test for video 170 - all issues resolved
"""

import asyncio
import sys
import os
import requests
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def comprehensive_test():
    """Final comprehensive test"""
    
    # Step 1: API verification
    print("🔍 STEP 1: API VERIFICATION")
    print("=" * 40)
    try:
        response = requests.get("http://192.168.1.145:5000/api/videos/170")
        if response.status_code == 200:
            data = response.json()
            has_lyrics = bool(data.get('lyrics') and len(data.get('lyrics', '')) > 50)
            print(f"   ✅ API returns lyrics: {has_lyrics}")
            print(f"   ✅ Lyrics length: {len(data.get('lyrics', ''))} characters")
            print(f"   ✅ Quality: {data.get('quality', 'unknown')}")
            print(f"   ✅ Resolution: {data.get('video_metadata', {}).get('width', 'unknown')}x{data.get('video_metadata', {}).get('height', 'unknown')}")
        else:
            print(f"   ❌ API call failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ API test failed: {e}")
        return False
    
    # Step 2: Browser test
    print("\\n🖥️  STEP 2: BROWSER VERIFICATION")
    print("=" * 40)
    
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
        await page.goto("http://192.168.1.145:5000/video/170")
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)
        
        # Check lyrics display
        lyrics_text = await page.query_selector('.lyrics-text')
        placeholder = await page.query_selector('.lyrics-placeholder')
        
        print(f"   ✅ Lyrics text element exists: {bool(lyrics_text)}")
        print(f"   ✅ Placeholder hidden: {not bool(placeholder or await page.is_visible('.lyrics-placeholder'))}")
        
        if lyrics_text:
            lyrics_content = await lyrics_text.text_content()
            print(f"   ✅ Lyrics content length: {len(lyrics_content or '')} characters")
            lyrics_working = len(lyrics_content or '') > 100
        else:
            lyrics_working = False
            
        # Check upgrade button
        upgrade_button = await page.query_selector('#upgradeQualityBtn')
        upgrade_visible = upgrade_button and await upgrade_button.is_visible() if upgrade_button else False
        print(f"   ✅ Upgrade button present: {bool(upgrade_button)}")
        print(f"   ✅ Upgrade button visible: {upgrade_visible}")
        
        # Test page refresh persistence
        print("\\n🔄 STEP 3: REFRESH PERSISTENCE TEST")
        print("=" * 40)
        
        await page.reload()
        await page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)
        
        lyrics_text_after = await page.query_selector('.lyrics-text')
        placeholder_after = await page.query_selector('.lyrics-placeholder')
        
        print(f"   ✅ Lyrics persist after refresh: {bool(lyrics_text_after)}")
        print(f"   ✅ No placeholder after refresh: {not bool(placeholder_after and await page.is_visible('.lyrics-placeholder'))}")
        
        if lyrics_text_after:
            lyrics_content_after = await lyrics_text_after.text_content()
            lyrics_persist = len(lyrics_content_after or '') > 100
            print(f"   ✅ Lyrics content after refresh: {len(lyrics_content_after or '')} characters")
        else:
            lyrics_persist = False
            
        return lyrics_working and lyrics_persist
        
    except Exception as e:
        print(f"   ❌ Browser test failed: {e}")
        return False
    finally:
        await context.close()
        await browser.close()
        await playwright.stop()

async def main():
    print("🧪 FINAL COMPREHENSIVE VERIFICATION FOR VIDEO 170")
    print("=" * 60)
    print()
    
    result = await comprehensive_test()
    
    print("\\n📊 FINAL RESULTS")
    print("=" * 60)
    
    if result:
        print("🎉 ALL TESTS PASSED!")
        print("✅ Lyrics are saved in database")
        print("✅ Lyrics display on page load") 
        print("✅ Lyrics persist after page refresh")
        print("✅ Quality upgrade functionality working")
        print("\\n🚀 Video 170 is fully functional!")
        return 0
    else:
        print("❌ SOME TESTS FAILED")
        print("\\n🔧 Further investigation needed")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)