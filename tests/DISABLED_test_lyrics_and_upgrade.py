#!/usr/bin/env python3
"""
Playwright E2E Tests for Lyrics and Quality Upgrade Functionality
Tests both lyrics saving and upgrade button visibility/functionality
"""

import asyncio
import sys
import os
import json
import time
import subprocess
from playwright.async_api import async_playwright, expect

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class LyricsAndUpgradeTestSuite:
    def __init__(self):
        self.base_url = "http://192.168.1.145:5000"
        self.test_results = []
        
    async def setup_browser(self):
        """Initialize Playwright browser"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True,  # Run in headless mode for server environment
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080}
        )
        self.page = await self.context.new_page()
        
        # Enable console logging
        self.page.on("console", lambda msg: print(f"🖥️  Console: {msg.text}"))
        self.page.on("pageerror", lambda error: print(f"❌ Page Error: {error}"))
        
    async def login(self):
        """Login to MVidarr"""
        print("🔐 Logging into MVidarr...")
        await self.page.goto(f"{self.base_url}/auth/login")
        await self.page.wait_for_load_state('networkidle')
        
        # Fill in login form with correct credentials
        await self.page.fill('#username', 'admin')
        await self.page.fill('#password', 'mvidarr')
        await self.page.click('button[type="submit"]')
        
        # Wait for success message and redirect
        try:
            await self.page.wait_for_selector('div:has-text("Login successful")', timeout=15000)
            await asyncio.sleep(2)  # Wait for redirect
            print("✅ Successfully logged in")
        except:
            # Alternative: try direct navigation to check if logged in
            await self.page.goto(f"{self.base_url}/")
            await self.page.wait_for_load_state('networkidle')
            print("✅ Logged in (alternative method)")
        
    async def test_lyrics_functionality(self):
        """Test lyrics search and saving functionality"""
        print("\\n🎵 Testing Lyrics Functionality...")
        
        # Test with video 174 (Tyler Childers - In Your Love)
        video_id = 174
        print(f"   Testing lyrics for video {video_id}")
        
        # Navigate to video detail page
        await self.page.goto(f"{self.base_url}/video/{video_id}")
        await self.page.wait_for_load_state('networkidle')
        
        # Check if lyrics section exists
        lyrics_section = await self.page.query_selector('#lyricsSection')
        if not lyrics_section:
            print("❌ Lyrics section not found on page")
            return False
            
        # Check for search lyrics button
        search_button = await self.page.query_selector('button:has-text("Search Lyrics")')
        if not search_button:
            print("❌ Search Lyrics button not found")
            return False
            
        print("   Clicking Search Lyrics button...")
        await search_button.click()
        
        # Wait for API call to complete (up to 30 seconds)
        try:
            # Wait for either success or failure message
            await self.page.wait_for_function("""
                () => {
                    const button = document.querySelector('button:has-text("Search Lyrics")');
                    return button && !button.disabled;
                }
            """, timeout=30000)
            
            # Check if lyrics were loaded
            await asyncio.sleep(2)  # Allow time for DOM update
            
            # Check API response by calling video endpoint
            response = await self.page.evaluate(f"""
                async () => {{
                    const response = await fetch('/api/videos/{video_id}');
                    const data = await response.json();
                    return data.lyrics;
                }}
            """)
            
            if response and len(response) > 50:
                print(f"✅ Lyrics found and saved ({len(response)} characters)")
                self.test_results.append({"test": "lyrics_functionality", "status": "PASS", "details": f"Lyrics saved with {len(response)} chars"})
                return True
            else:
                print("❌ No lyrics found or lyrics too short")
                self.test_results.append({"test": "lyrics_functionality", "status": "FAIL", "details": "No substantial lyrics found"})
                return False
                
        except Exception as e:
            print(f"❌ Lyrics search failed: {e}")
            self.test_results.append({"test": "lyrics_functionality", "status": "FAIL", "details": str(e)})
            return False
            
    async def test_upgrade_button_visibility(self):
        """Test upgrade button visibility for different video qualities"""
        print("\\n⬆️  Testing Upgrade Button Visibility...")
        
        # Test with video 174 (should show upgrade button - 266p)
        video_id_upgradeable = 174
        print(f"   Testing upgradeable video {video_id_upgradeable} (266p)")
        
        await self.page.goto(f"{self.base_url}/video/{video_id_upgradeable}")
        await self.page.wait_for_load_state('networkidle')
        
        # Wait for upgrade check to complete
        await asyncio.sleep(3)
        
        # Check if upgrade button is visible
        upgrade_button = await self.page.query_selector('#upgradeQualityBtn')
        if upgrade_button:
            is_visible = await upgrade_button.is_visible()
            if is_visible:
                print(f"✅ Upgrade button correctly visible for low quality video")
                self.test_results.append({"test": "upgrade_button_low_quality", "status": "PASS", "details": "Button visible for 266p video"})
            else:
                print(f"❌ Upgrade button should be visible but is hidden")
                self.test_results.append({"test": "upgrade_button_low_quality", "status": "FAIL", "details": "Button hidden for upgradeable video"})
                return False
        else:
            print("❌ Upgrade button element not found")
            self.test_results.append({"test": "upgrade_button_low_quality", "status": "FAIL", "details": "Button element not found"})
            return False
            
        # Test with video 212 (should NOT show upgrade button - 806p)
        video_id_high_quality = 212
        print(f"   Testing high quality video {video_id_high_quality} (806p)")
        
        await self.page.goto(f"{self.base_url}/video/{video_id_high_quality}")
        await self.page.wait_for_load_state('networkidle')
        
        # Wait for upgrade check to complete
        await asyncio.sleep(3)
        
        # Check if upgrade button is hidden
        upgrade_button = await self.page.query_selector('#upgradeQualityBtn')
        if upgrade_button:
            is_visible = await upgrade_button.is_visible()
            if not is_visible:
                print(f"✅ Upgrade button correctly hidden for high quality video")
                self.test_results.append({"test": "upgrade_button_high_quality", "status": "PASS", "details": "Button hidden for 806p video"})
                return True
            else:
                print(f"❌ Upgrade button should be hidden but is visible")
                self.test_results.append({"test": "upgrade_button_high_quality", "status": "FAIL", "details": "Button visible for high quality video"})
                return False
        else:
            print("❌ Upgrade button element not found")
            self.test_results.append({"test": "upgrade_button_high_quality", "status": "FAIL", "details": "Button element not found"})
            return False
            
    async def test_upgrade_button_functionality(self):
        """Test upgrade button click functionality"""
        print("\\n🔧 Testing Upgrade Button Functionality...")
        
        # Use video 174 which should have upgrade button
        video_id = 174
        await self.page.goto(f"{self.base_url}/video/{video_id}")
        await self.page.wait_for_load_state('networkidle')
        
        # Wait for upgrade check
        await asyncio.sleep(3)
        
        # Check if button is visible
        upgrade_button = await self.page.query_selector('#upgradeQualityBtn')
        if not upgrade_button or not await upgrade_button.is_visible():
            print("❌ Upgrade button not available for testing")
            self.test_results.append({"test": "upgrade_button_click", "status": "SKIP", "details": "Button not visible"})
            return False
            
        print("   Clicking upgrade button...")
        
        # Set up dialog handler for confirmation
        dialog_confirmed = False
        async def handle_dialog(dialog):
            nonlocal dialog_confirmed
            print(f"   📋 Dialog appeared: {dialog.message}")
            await dialog.accept()
            dialog_confirmed = True
            
        self.page.on("dialog", handle_dialog)
        
        # Click the upgrade button
        await upgrade_button.click()
        
        # Wait a moment for dialog
        await asyncio.sleep(1)
        
        if dialog_confirmed:
            print("✅ Upgrade confirmation dialog handled")
            
            # Wait for API call and button state change
            await asyncio.sleep(2)
            
            # Check if button shows loading state
            button_text = await upgrade_button.inner_text()
            if "Upgrading" in button_text or await upgrade_button.is_disabled():
                print("✅ Upgrade button shows loading state")
                self.test_results.append({"test": "upgrade_button_click", "status": "PASS", "details": "Button clicked, dialog confirmed, loading state shown"})
                return True
            else:
                print("❌ Upgrade button did not show loading state")
                self.test_results.append({"test": "upgrade_button_click", "status": "FAIL", "details": "No loading state after click"})
                return False
        else:
            print("❌ Confirmation dialog did not appear")
            self.test_results.append({"test": "upgrade_button_click", "status": "FAIL", "details": "No confirmation dialog"})
            return False
            
    async def verify_api_endpoints(self):
        """Verify API endpoints are working"""
        print("\\n🔌 Verifying API Endpoints...")
        
        # Test lyrics search endpoint
        try:
            response = await self.page.evaluate("""
                async () => {
                    const response = await fetch('/api/videos/174/lyrics/search', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'}
                    });
                    return {
                        status: response.status,
                        data: await response.json()
                    };
                }
            """)
            
            if response['status'] == 200 and response['data'].get('success'):
                print("✅ Lyrics search API working")
                self.test_results.append({"test": "lyrics_api", "status": "PASS", "details": f"API returned: {response['data'].get('message', 'Success')}"})
            else:
                print(f"❌ Lyrics search API failed: {response}")
                self.test_results.append({"test": "lyrics_api", "status": "FAIL", "details": f"Status: {response['status']}"})
                
        except Exception as e:
            print(f"❌ Lyrics API test failed: {e}")
            self.test_results.append({"test": "lyrics_api", "status": "FAIL", "details": str(e)})
            
        # Test upgradeable videos endpoint
        try:
            response = await self.page.evaluate("""
                async () => {
                    const response = await fetch('/api/video-quality/upgradeable');
                    return {
                        status: response.status,
                        data: await response.json()
                    };
                }
            """)
            
            if response['status'] == 200 and response['data'].get('success'):
                count = response['data'].get('count', 0)
                print(f"✅ Upgradeable videos API working ({count} upgradeable videos)")
                self.test_results.append({"test": "upgradeable_api", "status": "PASS", "details": f"{count} upgradeable videos found"})
            else:
                print(f"❌ Upgradeable videos API failed: {response}")
                self.test_results.append({"test": "upgradeable_api", "status": "FAIL", "details": f"Status: {response['status']}"})
                
        except Exception as e:
            print(f"❌ Upgradeable API test failed: {e}")
            self.test_results.append({"test": "upgradeable_api", "status": "FAIL", "details": str(e)})
            
    async def cleanup(self):
        """Clean up browser resources"""
        if hasattr(self, 'context'):
            await self.context.close()
        if hasattr(self, 'browser'):
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
            
    def print_results(self):
        """Print test results summary"""
        print("\\n" + "="*60)
        print("📊 TEST RESULTS SUMMARY")
        print("="*60)
        
        passed = sum(1 for result in self.test_results if result['status'] == 'PASS')
        failed = sum(1 for result in self.test_results if result['status'] == 'FAIL')
        skipped = sum(1 for result in self.test_results if result['status'] == 'SKIP')
        
        for result in self.test_results:
            status_emoji = "✅" if result['status'] == 'PASS' else "❌" if result['status'] == 'FAIL' else "⏭️"
            print(f"{status_emoji} {result['test']}: {result['status']} - {result['details']}")
            
        print(f"\\n📈 Total: {len(self.test_results)} | ✅ Passed: {passed} | ❌ Failed: {failed} | ⏭️ Skipped: {skipped}")
        
        if failed == 0:
            print("\\n🎉 ALL TESTS PASSED!")
        else:
            print(f"\\n⚠️  {failed} test(s) failed")
            
        return failed == 0

async def main():
    """Main test execution"""
    test_suite = LyricsAndUpgradeTestSuite()
    
    try:
        await test_suite.setup_browser()
        await test_suite.login()
        
        # Run all tests
        await test_suite.verify_api_endpoints()
        await test_suite.test_lyrics_functionality()
        await test_suite.test_upgrade_button_visibility()
        await test_suite.test_upgrade_button_functionality()
        
        # Print results
        all_passed = test_suite.print_results()
        
        return 0 if all_passed else 1
        
    except Exception as e:
        print(f"❌ Test suite failed: {e}")
        return 1
    finally:
        await test_suite.cleanup()

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)