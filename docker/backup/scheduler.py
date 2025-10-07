#!/usr/bin/env python3
"""
MVidarr Backup Scheduler
Handles automated backup scheduling for self-hosted deployments
"""

import logging
import os
import subprocess
import schedule
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/backups/scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BackupScheduler:
    def __init__(self):
        self.backup_schedule = os.getenv('BACKUP_SCHEDULE', '0 2 * * *')  # Daily at 2 AM
        self.backup_enabled = os.getenv('BACKUP_ENABLED', 'true').lower() == 'true'
        
        # Parse cron-like schedule to schedule library format
        self.parse_schedule()

    def parse_schedule(self):
        """Parse cron-like schedule format"""
        try:
            # Format: minute hour day month weekday
            parts = self.backup_schedule.split()
            
            if len(parts) != 5:
                logger.warning(f"Invalid schedule format: {self.backup_schedule}, using default")
                self.schedule_backup_daily()
                return
            
            minute, hour, day, month, weekday = parts
            
            # Handle different schedule patterns
            if weekday != '*':
                # Weekly schedule
                weekday_map = {
                    '0': 'sunday', '1': 'monday', '2': 'tuesday', 
                    '3': 'wednesday', '4': 'thursday', '5': 'friday', '6': 'saturday'
                }
                day_name = weekday_map.get(weekday, 'sunday')
                time_str = f"{hour.zfill(2)}:{minute.zfill(2)}"
                getattr(schedule.every(), day_name).at(time_str).do(self.run_backup)
                logger.info(f"Scheduled weekly backup on {day_name} at {time_str}")
                
            elif day != '*':
                # Monthly schedule (simplified - runs on specific day each month)
                time_str = f"{hour.zfill(2)}:{minute.zfill(2)}"
                schedule.every().day.at(time_str).do(self.check_monthly_backup, target_day=int(day))
                logger.info(f"Scheduled monthly backup on day {day} at {time_str}")
                
            else:
                # Daily schedule
                time_str = f"{hour.zfill(2)}:{minute.zfill(2)}"
                schedule.every().day.at(time_str).do(self.run_backup)
                logger.info(f"Scheduled daily backup at {time_str}")
                
        except Exception as e:
            logger.error(f"Failed to parse schedule: {e}")
            self.schedule_backup_daily()

    def schedule_backup_daily(self):
        """Default daily backup at 2 AM"""
        schedule.every().day.at("02:00").do(self.run_backup)
        logger.info("Scheduled default daily backup at 02:00")

    def check_monthly_backup(self, target_day):
        """Check if today matches target day for monthly backup"""
        if datetime.now().day == target_day:
            self.run_backup()

    def run_backup(self):
        """Execute backup script"""
        if not self.backup_enabled:
            logger.info("Backup is disabled, skipping")
            return
            
        logger.info("Starting scheduled backup...")
        
        try:
            # Run backup script
            result = subprocess.run(
                ['/app/backup.sh'],
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode == 0:
                logger.info("Backup completed successfully")
                logger.info(f"Backup output: {result.stdout}")
            else:
                logger.error(f"Backup failed with return code {result.returncode}")
                logger.error(f"Backup error: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            logger.error("Backup timed out after 1 hour")
        except Exception as e:
            logger.error(f"Backup failed: {e}")

    def health_check(self):
        """Simple health check for the scheduler"""
        try:
            # Check if backup directory is accessible
            backup_dir = '/app/backups'
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
                
            # Check if last backup is recent (within 25 hours for daily backups)
            last_backup_file = os.path.join(backup_dir, 'last_backup.txt')
            if os.path.exists(last_backup_file):
                with open(last_backup_file, 'r') as f:
                    last_backup_time = int(f.read().strip())
                    
                time_since_backup = time.time() - last_backup_time
                if time_since_backup > 90000:  # 25 hours
                    logger.warning(f"Last backup was {time_since_backup/3600:.1f} hours ago")
                    
            # Write health check timestamp
            with open(os.path.join(backup_dir, 'scheduler_health.txt'), 'w') as f:
                f.write(str(int(time.time())))
                
        except Exception as e:
            logger.error(f"Health check failed: {e}")

    def run(self):
        """Main scheduler loop"""
        logger.info("Starting MVidarr Backup Scheduler")
        logger.info(f"Backup enabled: {self.backup_enabled}")
        logger.info(f"Schedule: {self.backup_schedule}")
        
        # Schedule health check every 5 minutes
        schedule.every(5).minutes.do(self.health_check)
        
        # Initial health check
        self.health_check()
        
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
                
            except KeyboardInterrupt:
                logger.info("Scheduler stopped by user")
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                time.sleep(60)

if __name__ == '__main__':
    scheduler = BackupScheduler()
    scheduler.run()