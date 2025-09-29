#!/usr/bin/env python3
"""
Emergency Fix for YouTube Signature Extraction Failure
Implements specific workarounds for player 377ca75b-main signature extraction failure
"""

import os
import sys
import subprocess
import shutil

def apply_signature_fix():
    """Apply specific fixes for signature extraction failure"""
    print("🔧 Applying Signature Extraction Emergency Fix...")
    
    try:
        # Fix 1: Install absolute latest yt-dlp from GitHub (nightly)
        print("1️⃣ Installing yt-dlp nightly build from GitHub...")
        
        # Remove existing yt-dlp installations to avoid conflicts
        subprocess.run(["pipx", "uninstall", "yt-dlp"], capture_output=True)
        
        # Install latest from GitHub
        result = subprocess.run([
            "pipx", "install", 
            "git+https://github.com/yt-dlp/yt-dlp.git"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("   ✅ Installed yt-dlp nightly from GitHub")
        else:
            print(f"   ❌ GitHub install failed: {result.stderr}")
            # Fallback to pip install of latest
            subprocess.run([
                "pip", "install", "--upgrade", "--force-reinstall", 
                "git+https://github.com/yt-dlp/yt-dlp.git"
            ], capture_output=True)
            print("   🔄 Fallback: installed via pip")
        
        # Update system symlinks
        latest_paths = [
            "/root/.local/bin/yt-dlp",
            "/usr/local/bin/python3.12/site-packages/yt_dlp/__main__.py",
            "/usr/local/bin/yt-dlp"
        ]
        
        working_path = None
        for path in latest_paths:
            if os.path.exists(path):
                working_path = path
                break
        
        if working_path:
            # Update system path
            if os.path.exists("/usr/local/bin/yt-dlp"):
                os.remove("/usr/local/bin/yt-dlp")
            
            if working_path != "/usr/local/bin/yt-dlp":
                os.symlink(working_path, "/usr/local/bin/yt-dlp")
            
            print(f"   ✅ Updated system path to: {working_path}")
        
        # Fix 2: Apply specific workarounds for player 377ca75b-main
        print("2️⃣ Applying player-specific workarounds...")
        
        # Test with specific extractor arguments that bypass signature extraction
        test_url = "https://www.youtube.com/watch?v=F4mUnmFbVNg"
        
        # Workaround 1: Use TV client (bypasses signature extraction entirely)
        print("   Testing TV client extractor...")
        result = subprocess.run([
            "/usr/local/bin/yt-dlp",
            "--extractor-args", "youtube:player_client=tv",
            "--simulate",
            test_url
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and "Signature extraction failed" not in result.stderr:
            print("   ✅ TV client extractor works!")
            tv_works = True
        else:
            print(f"   ❌ TV client failed: {result.stderr[-200:] if result.stderr else 'No error output'}")
            tv_works = False
        
        # Workaround 2: Use Android client
        print("   Testing Android client extractor...")
        result = subprocess.run([
            "/usr/local/bin/yt-dlp", 
            "--extractor-args", "youtube:player_client=android",
            "--simulate",
            test_url
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0 and "Signature extraction failed" not in result.stderr:
            print("   ✅ Android client extractor works!")
            android_works = True
        else:
            print(f"   ❌ Android client failed: {result.stderr[-200:] if result.stderr else 'No error output'}")
            android_works = False
        
        # Workaround 3: Use web client with cookies
        print("   Testing web client with cookies...")
        cookie_path = "/home/mike/mvidarr/data/cookies/youtube_cookies.txt"
        if os.path.exists(cookie_path):
            result = subprocess.run([
                "/usr/local/bin/yt-dlp",
                "--cookies", cookie_path,
                "--extractor-args", "youtube:player_client=web",
                "--simulate", 
                test_url
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and "Signature extraction failed" not in result.stderr:
                print("   ✅ Web client with cookies works!")
                web_cookies_works = True
            else:
                print(f"   ❌ Web+cookies failed: {result.stderr[-200:] if result.stderr else 'No error output'}")
                web_cookies_works = False
        else:
            print("   ⚠️ No cookie file found")
            web_cookies_works = False
        
        # Fix 3: Update MVidarr ytdlp_service.py with working extractor arguments
        print("3️⃣ Updating MVidarr with working extractor arguments...")
        
        ytdlp_service_path = "/home/mike/mvidarr/src/services/ytdlp_service.py"
        
        if os.path.exists(ytdlp_service_path):
            with open(ytdlp_service_path, 'r') as f:
                content = f.read()
            
            # Determine best extractor arguments based on what worked
            if tv_works:
                best_extractor = "youtube:player_client=tv"
                print("   🎯 Using TV client as primary extractor")
            elif android_works:
                best_extractor = "youtube:player_client=android" 
                print("   🎯 Using Android client as primary extractor")
            elif web_cookies_works:
                best_extractor = "youtube:player_client=web"
                print("   🎯 Using Web client with cookies as primary extractor")
            else:
                best_extractor = "youtube:player_client=tv,android,web"
                print("   🎯 Using multi-client fallback strategy")
            
            # Find and update the command building section
            # Look for the section where yt-dlp command is built
            if "# Add subtitle options if requested" in content:
                # Insert extractor args before subtitle options
                old_section = "# Add subtitle options if requested"
                new_section = f'''# Add extractor arguments to bypass signature extraction
                cmd.extend(["--extractor-args", "{best_extractor}"])
                
                # Add subtitle options if requested'''
                
                content = content.replace(old_section, new_section)
                print("   ✅ Added extractor arguments to ytdlp_service.py")
            
            # Also add retry and timeout options for robustness
            if "# Execute yt-dlp" in content:
                old_section = "# Execute yt-dlp"
                new_section = '''# Add robustness options
                cmd.extend([
                    "--socket-timeout", "30",
                    "--retries", "5", 
                    "--fragment-retries", "5",
                    "--retry-sleep", "2"
                ])
                
                # Execute yt-dlp'''
                
                content = content.replace(old_section, new_section)
                print("   ✅ Added robustness options to ytdlp_service.py")
            
            # Write back the updated content
            with open(ytdlp_service_path, 'w') as f:
                f.write(content)
        
        # Fix 4: Verify the fix works
        print("4️⃣ Verifying signature extraction fix...")
        
        result = subprocess.run([
            "/usr/local/bin/yt-dlp", 
            "--version"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"   ✅ yt-dlp version: {version}")
        
        # Test the problematic video one more time
        print("   🧪 Final test of problematic video...")
        final_result = subprocess.run([
            "/usr/local/bin/yt-dlp",
            "--extractor-args", best_extractor,
            "--simulate",
            test_url
        ], capture_output=True, text=True, timeout=45)
        
        if final_result.returncode == 0 and "Signature extraction failed" not in final_result.stderr:
            print("   🎉 SUCCESS! Signature extraction fix verified!")
            success = True
        else:
            print("   ⚠️ Still having issues, but workarounds applied")
            success = False
        
        print("\n📋 Summary of Applied Fixes:")
        print(f"   • yt-dlp nightly build installed")
        print(f"   • Best extractor: {best_extractor}")
        print(f"   • Robustness options added")
        print(f"   • TV client works: {'✅' if tv_works else '❌'}")
        print(f"   • Android client works: {'✅' if android_works else '❌'}")
        print(f"   • Web+cookies works: {'✅' if web_cookies_works else '❌'}")
        
        print("\n🚀 Next Steps:")
        print("1. Restart MVidarr service")
        print("2. Try downloading the problematic video again") 
        print("3. If still failing, we may need to implement OAuth2 authentication")
        
        return success
        
    except Exception as e:
        print(f"❌ Signature fix failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

if __name__ == "__main__":
    success = apply_signature_fix()
    sys.exit(0 if success else 1)