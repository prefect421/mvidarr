#!/usr/bin/env python3
"""
Comprehensive Test for Video 170 - Tyler Childers - Eatin' Big Time
Tests the specific issues:
1. Lyrics not persisting after page refresh
2. Upgrade button not actually downloading higher quality
"""

import asyncio
import sys
import os
import json
import time
import requests
from playwright.async_api import async_playwright, expect

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class Video170ComprehensiveTest:
    def __init__(self):
        self.base_url = "http://192.168.1.145:5000"
        self.test_video_id = 170
        self.results = []
        
    async def setup_browser(self):
        """Initialize Playwright browser"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        self.page = await self.context.new_page()
        
        # Enable console and error logging
        self.page.on("console", lambda msg: print(f"🖥️  Console: {msg.text}"))
        self.page.on("pageerror", lambda error: print(f"❌ Page Error: {error}"))
        
    async def login(self):
        """Login to MVidarr"""
        print("🔐 Logging into MVidarr...")
        await self.page.goto(f"{self.base_url}/auth/login")
        await self.page.wait_for_load_state('networkidle')
        
        await self.page.fill('#username', 'admin')
        await self.page.fill('#password', 'mvidarr')
        await self.page.click('button[type="submit"]')
        
        try:
            await self.page.wait_for_selector('div:has-text("Login successful")', timeout=15000)
            await asyncio.sleep(2)
            print("✅ Successfully logged in")
        except:
            await self.page.goto(f"{self.base_url}/")
            await self.page.wait_for_load_state('networkidle')
            print("✅ Logged in (fallback)")
            
    def get_video_data_via_api(self):
        """Get current video data via API"""
        try:
            response = requests.get(f"{self.base_url}/api/videos/{self.test_video_id}")
            if response.status_code == 200:
                return response.json()
            else:
                print(f"❌ API call failed: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ API call exception: {e}")
            return None
            
    async def test_lyrics_persistence_after_refresh(self):
        """Test if lyrics persist after page refresh"""
        print(f"\\n🎵 Testing Lyrics Persistence for Video {self.test_video_id}...")
        
        # Step 1: Get initial video data
        initial_data = self.get_video_data_via_api()
        if not initial_data:
            self.results.append({"test": "lyrics_persistence", "status": "FAIL", "reason": "Could not get initial video data"})
            return False
            
        print(f"   Initial lyrics in database: {'YES' if initial_data.get('lyrics') else 'NO'}")
        print(f"   Initial lyrics length: {len(initial_data.get('lyrics', '')) if initial_data.get('lyrics') else 0} characters")
        
        # Step 2: Navigate to video page
        await self.page.goto(f"{self.base_url}/video/{self.test_video_id}")
        await self.page.wait_for_load_state('networkidle')
        
        # Step 3: Check if lyrics are displayed on first load
        await asyncio.sleep(2)  # Allow time for any dynamic loading
        
        lyrics_content = await self.page.evaluate("""
            () => {
                const lyricsContainer = document.querySelector('#lyricsContent');
                return lyricsContainer ? lyricsContainer.textContent.trim() : '';
            }
        """)
        
        print(f"   Lyrics displayed on first load: {'YES' if lyrics_content else 'NO'}")
        print(f"   Displayed lyrics length: {len(lyrics_content)} characters")
        
        # Step 4: Refresh the page
        print("   Refreshing page...")
        await self.page.reload()
        await self.page.wait_for_load_state('networkidle')
        await asyncio.sleep(2)  # Allow time for any dynamic loading
        
        # Step 5: Check if lyrics are still displayed after refresh
        lyrics_content_after_refresh = await self.page.evaluate("""
            () => {
                const lyricsContainer = document.querySelector('#lyricsContent');
                return lyricsContainer ? lyricsContainer.textContent.trim() : '';
            }
        """)
        
        print(f"   Lyrics displayed after refresh: {'YES' if lyrics_content_after_refresh else 'NO'}")
        print(f"   Displayed lyrics length after refresh: {len(lyrics_content_after_refresh)} characters")
        
        # Step 6: Verify API still has lyrics
        final_data = self.get_video_data_via_api()
        api_has_lyrics = bool(final_data and final_data.get('lyrics'))
        print(f"   API still has lyrics: {'YES' if api_has_lyrics else 'NO'}")
        
        # Determine test result
        if initial_data.get('lyrics') and lyrics_content_after_refresh:
            print("✅ Lyrics persistence test PASSED")
            self.results.append({"test": "lyrics_persistence", "status": "PASS", "reason": "Lyrics persist after refresh"})
            return True
        elif initial_data.get('lyrics') and not lyrics_content_after_refresh:
            print("❌ Lyrics persistence test FAILED - Lyrics in DB but not displayed after refresh")
            self.results.append({"test": "lyrics_persistence", "status": "FAIL", "reason": "Lyrics in database but not displayed after page refresh"})
            return False
        else:
            print("❌ Lyrics persistence test FAILED - No lyrics in database to test")
            self.results.append({"test": "lyrics_persistence", "status": "FAIL", "reason": "No lyrics in database"})
            return False
            
    async def test_upgrade_button_actual_quality_improvement(self):
        """Test if upgrade button actually downloads higher quality"""
        print(f"\\n⬆️  Testing Actual Quality Upgrade for Video {self.test_video_id}...")
        
        # Step 1: Get initial quality info
        initial_data = self.get_video_data_via_api()
        if not initial_data:
            self.results.append({"test": "upgrade_quality", "status": "FAIL", "reason": "Could not get initial video data"})
            return False
            
        initial_quality = initial_data.get('quality', 'unknown')
        initial_file_size = initial_data.get('video_metadata', {}).get('file_size', 0)
        initial_height = initial_data.get('video_metadata', {}).get('height', 0)
        initial_file_path = initial_data.get('local_path', '')
        
        print(f"   Initial quality: {initial_quality}")
        print(f"   Initial file size: {initial_file_size} bytes")
        print(f"   Initial height: {initial_height}p")
        print(f"   Initial file path: {initial_file_path}")
        
        # Step 2: Navigate to video page
        await self.page.goto(f"{self.base_url}/video/{self.test_video_id}")
        await self.page.wait_for_load_state('networkidle')
        await asyncio.sleep(3)  # Wait for upgrade check
        
        # Step 3: Check if upgrade button is visible
        upgrade_button = await self.page.query_selector('#upgradeQualityBtn')
        if not upgrade_button:
            print("❌ Upgrade button not found")
            self.results.append({"test": "upgrade_quality", "status": "FAIL", "reason": "Upgrade button not found"})
            return False
            
        is_visible = await upgrade_button.is_visible()
        if not is_visible:
            print("❌ Upgrade button not visible")
            self.results.append({"test": "upgrade_quality", "status": "FAIL", "reason": "Upgrade button not visible"})
            return False
            
        print("✅ Upgrade button is visible")
        
        # Step 4: Trigger the upgrade
        print("   Triggering quality upgrade...")
        
        # Handle the confirmation dialog
        dialog_handled = False
        async def handle_dialog(dialog):
            nonlocal dialog_handled
            print(f"   📋 Confirmation dialog: {dialog.message[:100]}...")
            await dialog.accept()
            dialog_handled = True
            
        self.page.on("dialog", handle_dialog)
        
        # Click the upgrade button
        await upgrade_button.click()
        await asyncio.sleep(1)
        
        if not dialog_handled:
            print("❌ No confirmation dialog appeared")
            self.results.append({"test": "upgrade_quality", "status": "FAIL", "reason": "No confirmation dialog"})
            return False
            
        print("✅ Upgrade triggered successfully")
        
        # Step 5: Wait for upgrade to complete (up to 3 minutes)
        print("   Waiting for upgrade to complete (max 3 minutes)...")
        upgrade_completed = False
        
        for i in range(36):  # 36 * 5 seconds = 3 minutes
            await asyncio.sleep(5)
            
            # Check if upgrade job completed
            current_data = self.get_video_data_via_api()
            if current_data:
                current_quality = current_data.get('quality', 'unknown')
                current_file_size = current_data.get('video_metadata', {}).get('file_size', 0)
                current_height = current_data.get('video_metadata', {}).get('height', 0)
                current_file_path = current_data.get('local_path', '')
                
                # Check if quality actually improved
                if (current_height > initial_height or 
                    current_file_size > initial_file_size * 1.2 or  # At least 20% larger
                    current_file_path != initial_file_path):
                    
                    print(f"✅ Quality upgrade completed!")
                    print(f"   New quality: {current_quality}")
                    print(f"   New file size: {current_file_size} bytes")
                    print(f"   New height: {current_height}p")
                    print(f"   New file path: {current_file_path}")
                    
                    upgrade_completed = True
                    break
                    
            print(f"   Waiting... ({i*5}s elapsed)")
            
        if upgrade_completed:
            self.results.append({"test": "upgrade_quality", "status": "PASS", "reason": "Quality actually improved"})
            return True
        else:
            print("❌ Upgrade did not complete or quality did not improve after 3 minutes")
            final_data = self.get_video_data_via_api()
            final_quality = final_data.get('quality', 'unknown') if final_data else 'unknown'
            final_height = final_data.get('video_metadata', {}).get('height', 0) if final_data else 0
            
            self.results.append({
                "test": "upgrade_quality", 
                "status": "FAIL", 
                "reason": f"No quality improvement detected. Initial: {initial_height}p, Final: {final_height}p"
            })
            return False
            
    async def test_lyrics_search_functionality(self):
        """Test lyrics search button functionality"""
        print(f"\\n🔍 Testing Lyrics Search Functionality for Video {self.test_video_id}...")
        
        # Navigate to video page
        await self.page.goto(f"{self.base_url}/video/{self.test_video_id}")
        await self.page.wait_for_load_state('networkidle')
        
        # Look for lyrics search button
        search_button = await self.page.query_selector('button:text("Search Lyrics")')
        if not search_button:
            # Try alternative selectors
            search_button = await self.page.query_selector('[onclick*="searchLyrics"]')
        
        if search_button:
            print("✅ Lyrics search button found")
            
            # Get initial lyrics state
            initial_data = self.get_video_data_via_api()
            had_lyrics_before = bool(initial_data and initial_data.get('lyrics'))
            
            print(f"   Had lyrics before search: {had_lyrics_before}")
            
            # Click search button
            await search_button.click()
            await asyncio.sleep(10)  # Wait for search to complete
            
            # Check if lyrics were found/updated
            final_data = self.get_video_data_via_api()
            has_lyrics_after = bool(final_data and final_data.get('lyrics'))
            
            print(f"   Has lyrics after search: {has_lyrics_after}")
            
            if has_lyrics_after:
                print("✅ Lyrics search functionality working")
                self.results.append({"test": "lyrics_search", "status": "PASS", "reason": "Lyrics search successful"})
                return True
            else:
                print("❌ Lyrics search did not find lyrics")
                self.results.append({"test": "lyrics_search", "status": "FAIL", "reason": "Lyrics search found no lyrics"})
                return False
        else:
            print("❌ Lyrics search button not found")
            self.results.append({"test": "lyrics_search", "status": "FAIL", "reason": "Search button not found"})
            return False
            
    async def cleanup(self):
        """Clean up browser resources"""
        if hasattr(self, 'context'):
            await self.context.close()
        if hasattr(self, 'browser'):
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
            
    def print_results(self):
        """Print comprehensive test results"""
        print("\\n" + "="*80)
        print(f"📊 COMPREHENSIVE TEST RESULTS FOR VIDEO {self.test_video_id}")
        print("="*80)
        
        for result in self.results:
            status_emoji = "✅" if result['status'] == 'PASS' else "❌"
            print(f"{status_emoji} {result['test'].upper()}: {result['status']}")
            print(f"    Reason: {result['reason']}")
            print()
            
        passed = sum(1 for r in self.results if r['status'] == 'PASS')
        failed = sum(1 for r in self.results if r['status'] == 'FAIL')
        
        print(f"📈 SUMMARY: {passed} PASSED, {failed} FAILED")
        
        if failed > 0:
            print("\\n🚨 ISSUES DETECTED - The functionality is NOT working correctly")
        else:
            print("\\n🎉 ALL TESTS PASSED - Functionality is working correctly")
            
        return failed == 0

async def main():
    """Main test execution"""
    test = Video170ComprehensiveTest()
    
    try:
        await test.setup_browser()
        await test.login()
        
        # Run comprehensive tests
        await test.test_lyrics_persistence_after_refresh()
        await test.test_lyrics_search_functionality()
        await test.test_upgrade_button_actual_quality_improvement()
        
        # Print results
        all_passed = test.print_results()
        
        return 0 if all_passed else 1
        
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        return 1
    finally:
        await test.cleanup()

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)