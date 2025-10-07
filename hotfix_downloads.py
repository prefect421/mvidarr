#!/usr/bin/env python3
"""
Immediate Hot Fix for Download Issues
Apply minimal changes to fix signature extraction without architectural changes
"""

import os
import sys
import shutil
import subprocess

def apply_hotfix():
    """Apply immediate hotfix for download issues"""
    print("🚑 Applying Emergency Download Hotfix...")
    
    try:
        # Fix 1: Ensure yt-dlp is latest version
        print("1️⃣ Updating yt-dlp to latest version...")
        
        # Update via pipx (preferred)
        result = subprocess.run(["pipx", "upgrade", "yt-dlp"], capture_output=True)
        if result.returncode == 0:
            print("   ✅ yt-dlp updated via pipx")
        else:
            # Fallback to direct update
            result = subprocess.run(["/root/.local/bin/yt-dlp", "-U"], capture_output=True)
            if result.returncode == 0:
                print("   ✅ yt-dlp updated directly")
            else:
                print("   ⚠️ yt-dlp update failed, proceeding with current version")
        
        # Fix 2: Revert to original ytdlp_service to avoid model conflicts
        print("2️⃣ Temporarily reverting to original service...")
        
        # Check if backup exists
        backup_dir = "backups/pre_unified_downloads"
        if os.path.exists(backup_dir):
            original_service = os.path.join(backup_dir, "ytdlp_service.py")
            if os.path.exists(original_service):
                # Copy back original service
                shutil.copy2(original_service, "src/services/ytdlp_service.py")
                print("   ✅ Reverted to original ytdlp_service.py")
                
                # Update imports back to original
                files_to_revert = [
                    "src/api/health.py",
                    "src/api/ytdlp.py", 
                    "src/api/fastapi/health.py",
                    "src/api/fastapi/ytdlp.py",
                    "src/api/fastapi/metube.py",
                    "src/api/metube.py"
                ]
                
                for file_path in files_to_revert:
                    if os.path.exists(file_path):
                        # Read file
                        with open(file_path, 'r') as f:
                            content = f.read()
                        
                        # Replace adapter import with original
                        content = content.replace(
                            "from src.services.download_service_adapter import ytdlp_service",
                            "from src.services.ytdlp_service import ytdlp_service"
                        )
                        
                        # Write back
                        with open(file_path, 'w') as f:
                            f.write(content)
                        
                        print(f"   ✅ Reverted imports in {file_path}")
        
        # Fix 3: Apply the critical path fix from earlier
        print("3️⃣ Applying critical path fixes...")
        
        # Ensure all paths point to the latest yt-dlp
        latest_path = "/root/.local/bin/yt-dlp"
        system_path = "/usr/local/bin/yt-dlp"
        
        if os.path.exists(latest_path):
            # Create/update symlink to ensure system uses latest
            if os.path.exists(system_path):
                os.remove(system_path)
            os.symlink(latest_path, system_path)
            print(f"   ✅ Linked {system_path} -> {latest_path}")
        
        # Fix 4: Check version
        print("4️⃣ Verifying yt-dlp version...")
        result = subprocess.run(["/usr/local/bin/yt-dlp", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            version = result.stdout.strip()
            print(f"   ✅ yt-dlp version: {version}")
            
            # Check if it's recent enough
            if "2025" in version:
                print("   ✅ Version looks current for 2025")
            else:
                print("   ⚠️ Version may be outdated for current YouTube requirements")
        
        print("\n🎉 Hotfix Applied Successfully!")
        print("📋 Next Steps:")
        print("1. Restart your MVidarr service")  
        print("2. Try downloading the videos again")
        print("3. Monitor logs for signature extraction errors")
        
        return True
        
    except Exception as e:
        print(f"❌ Hotfix failed: {e}")
        return False

if __name__ == "__main__":
    success = apply_hotfix()
    sys.exit(0 if success else 1)