"""
Collection Organizer Service - Phase 3 Week 28
Consumer-focused music video collection organization and management
"""

import asyncio
import hashlib
import json
import os
import shutil
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Set
import re

from src.utils.logger import get_logger
from src.services.redis_service import get_redis_client
from src.services.music_video_detector import get_music_video_detector, MusicVideoDetectionResult
from src.services.enhanced_artist_discovery_service import get_enhanced_artist_discovery
from src.services.genre_service import get_genre_service
from src.models.video import Video
from src.models.artist import Artist
from src.database import get_async_session

logger = get_logger("mvidarr.collection_organizer")

class OrganizationStrategy(Enum):
    """Organization strategies for music video collections"""
    ARTIST_TITLE = "artist_title"           # Artist/Title format
    ARTIST_ALBUM_TITLE = "artist_album_title"  # Artist/Album/Title format  
    GENRE_ARTIST = "genre_artist"           # Genre/Artist/Title format
    YEAR_ARTIST = "year_artist"             # Year/Artist/Title format
    FLAT_ARTIST_TITLE = "flat_artist_title" # Flat structure with Artist - Title
    CUSTOM = "custom"                        # User-defined custom structure

class OrganizationRule:
    """Rule for organizing music video collections"""
    
    def __init__(self):
        self.strategy: OrganizationStrategy = OrganizationStrategy.ARTIST_TITLE
        self.clean_filenames: bool = True
        self.preserve_quality_info: bool = True
        self.group_versions: bool = True  # Group different versions of same song
        self.handle_duplicates: bool = True
        self.create_artist_folders: bool = True
        self.sanitize_names: bool = True
        self.max_filename_length: int = 200
        self.custom_pattern: Optional[str] = None
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'strategy': self.strategy.value,
            'clean_filenames': self.clean_filenames,
            'preserve_quality_info': self.preserve_quality_info,
            'group_versions': self.group_versions,
            'handle_duplicates': self.handle_duplicates,
            'create_artist_folders': self.create_artist_folders,
            'sanitize_names': self.sanitize_names,
            'max_filename_length': self.max_filename_length,
            'custom_pattern': self.custom_pattern
        }

class OrganizationPlan:
    """Plan for organizing a music video collection"""
    
    def __init__(self):
        self.total_files: int = 0
        self.music_videos_found: int = 0
        self.organization_actions: List[Dict] = []
        self.estimated_time_seconds: float = 0.0
        self.disk_space_required: int = 0
        self.conflicts: List[Dict] = []
        self.warnings: List[str] = []
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_files': self.total_files,
            'music_videos_found': self.music_videos_found,
            'organization_actions': self.organization_actions,
            'estimated_time_seconds': self.estimated_time_seconds,
            'disk_space_required': self.disk_space_required,
            'conflicts': self.conflicts,
            'warnings': self.warnings
        }

class OrganizationResult:
    """Result of collection organization operation"""
    
    def __init__(self):
        self.success: bool = False
        self.files_processed: int = 0
        self.files_moved: int = 0
        self.files_renamed: int = 0
        self.folders_created: int = 0
        self.errors: List[Dict] = []
        self.warnings: List[str] = []
        self.processing_time_ms: float = 0.0
        self.organization_summary: Dict[str, Any] = {}
        
    def to_dict(self) -> Dict[str, Any]:
        return {
            'success': self.success,
            'files_processed': self.files_processed,
            'files_moved': self.files_moved,
            'files_renamed': self.files_renamed,
            'folders_created': self.folders_created,
            'errors': self.errors,
            'warnings': self.warnings,
            'processing_time_ms': self.processing_time_ms,
            'organization_summary': self.organization_summary
        }

class CollectionOrganizer:
    """Consumer-focused music video collection organizer"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.redis_client = None
        self.music_video_detector = None
        self.artist_discovery = None
        self.genre_service = None
        
        # Filename sanitization patterns
        self.invalid_chars = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
        self.multiple_spaces = re.compile(r'\s+')
        self.leading_trailing_dots = re.compile(r'^\.+|\.+$')
        
        # Quality/version indicators to preserve
        self.quality_indicators = [
            'HD', '720p', '1080p', '4K', 'HQ', 'Official', 
            'Live', 'Acoustic', 'Remix', 'Cover', 'Lyrics'
        ]
        
        # Reserved Windows filenames to avoid
        self.reserved_names = {
            'CON', 'PRN', 'AUX', 'NUL',
            'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
            'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
        }
    
    async def initialize(self):
        """Initialize organizer services"""
        try:
            self.redis_client = await get_redis_client()
            self.music_video_detector = await get_music_video_detector()
            self.artist_discovery = await get_enhanced_artist_discovery()
            self.genre_service = await get_genre_service()
            
            logger.info("Collection organizer initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize collection organizer: {e}")
            raise
    
    async def create_organization_plan(
        self, 
        source_directory: str, 
        target_directory: str,
        rules: OrganizationRule,
        scan_subdirs: bool = True
    ) -> OrganizationPlan:
        """Create a plan for organizing a music video collection"""
        start_time = asyncio.get_event_loop().time()
        plan = OrganizationPlan()
        
        try:
            # Ensure services are initialized
            if not self.redis_client:
                await self.initialize()
            
            logger.info(f"Creating organization plan for {source_directory} -> {target_directory}")
            
            # Find all video files
            video_files = await self._find_video_files(source_directory, scan_subdirs)
            plan.total_files = len(video_files)
            
            if not video_files:
                plan.warnings.append(f"No video files found in {source_directory}")
                return plan
            
            # Detect music videos in batch
            logger.info(f"Analyzing {len(video_files)} video files for music video content")
            detection_results = await self._batch_detect_videos(video_files)
            
            # Process each detected music video
            music_videos = []
            for i, (video_path, detection_result) in enumerate(zip(video_files, detection_results)):
                if detection_result.is_music_video:
                    music_videos.append((video_path, detection_result))
            
            plan.music_videos_found = len(music_videos)
            logger.info(f"Found {plan.music_videos_found} music videos out of {plan.total_files} files")
            
            # Create organization actions for each music video
            for video_path, detection_result in music_videos:
                action = await self._create_organization_action(
                    video_path, detection_result, target_directory, rules
                )
                
                if action:
                    plan.organization_actions.append(action)
                    plan.disk_space_required += action.get('file_size', 0)
                    
                    # Check for potential conflicts
                    conflict = await self._check_organization_conflict(action, plan.organization_actions[:-1])
                    if conflict:
                        plan.conflicts.append(conflict)
            
            # Estimate processing time (roughly 1 second per file + move time)
            plan.estimated_time_seconds = len(plan.organization_actions) * 1.5
            
            # Add warnings for low-confidence detections
            low_confidence_count = sum(
                1 for _, result in zip(video_files, detection_results)
                if result.confidence.value in ['low', 'very_low'] and result.is_music_video
            )
            
            if low_confidence_count > 0:
                plan.warnings.append(f"{low_confidence_count} files have low confidence music video detection")
            
            logger.info(f"Organization plan created: {plan.music_videos_found} music videos, "
                       f"{len(plan.organization_actions)} actions, "
                       f"{len(plan.conflicts)} conflicts")
            
            return plan
            
        except Exception as e:
            logger.error(f"Failed to create organization plan: {e}")
            plan.warnings.append(f"Error creating plan: {e}")
            return plan
    
    async def execute_organization_plan(
        self,
        plan: OrganizationPlan,
        dry_run: bool = False,
        progress_callback=None
    ) -> OrganizationResult:
        """Execute the organization plan"""
        start_time = asyncio.get_event_loop().time()
        result = OrganizationResult()
        
        try:
            logger.info(f"Executing organization plan: {len(plan.organization_actions)} actions "
                       f"(dry_run={dry_run})")
            
            created_folders = set()
            
            for i, action in enumerate(plan.organization_actions):
                try:
                    # Execute the organization action
                    action_result = await self._execute_organization_action(action, dry_run, created_folders)
                    
                    # Update result statistics
                    result.files_processed += 1
                    if action_result.get('moved'):
                        result.files_moved += 1
                    if action_result.get('renamed'):
                        result.files_renamed += 1
                    if action_result.get('folder_created'):
                        result.folders_created += 1
                    
                    # Update progress
                    if progress_callback:
                        await progress_callback(i + 1, len(plan.organization_actions), action)
                    
                except Exception as e:
                    error_info = {
                        'action': action,
                        'error': str(e),
                        'timestamp': datetime.now().isoformat()
                    }
                    result.errors.append(error_info)
                    logger.error(f"Failed to execute action {action.get('source_path', 'unknown')}: {e}")
            
            # Calculate success
            result.success = len(result.errors) == 0
            result.processing_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            
            # Create summary
            result.organization_summary = {
                'total_actions': len(plan.organization_actions),
                'successful_actions': result.files_processed - len(result.errors),
                'failed_actions': len(result.errors),
                'folders_created': result.folders_created,
                'dry_run': dry_run
            }
            
            logger.info(f"Organization plan execution completed: "
                       f"{result.files_processed} files processed, "
                       f"{len(result.errors)} errors, "
                       f"success={result.success}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to execute organization plan: {e}")
            result.success = False
            result.processing_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            result.errors.append({
                'error': f"Plan execution failed: {e}",
                'timestamp': datetime.now().isoformat()
            })
            return result
    
    async def organize_collection(
        self,
        source_directory: str,
        target_directory: str,
        rules: OrganizationRule,
        dry_run: bool = False,
        progress_callback=None
    ) -> OrganizationResult:
        """Complete collection organization in one step"""
        try:
            # Create plan
            plan = await self.create_organization_plan(source_directory, target_directory, rules)
            
            if not plan.organization_actions:
                result = OrganizationResult()
                result.success = True
                result.warnings.append("No music videos found to organize")
                return result
            
            # Execute plan
            return await self.execute_organization_plan(plan, dry_run, progress_callback)
            
        except Exception as e:
            logger.error(f"Failed to organize collection: {e}")
            result = OrganizationResult()
            result.success = False
            result.errors.append({
                'error': f"Collection organization failed: {e}",
                'timestamp': datetime.now().isoformat()
            })
            return result
    
    async def _find_video_files(self, directory: str, scan_subdirs: bool) -> List[str]:
        """Find all video files in directory"""
        video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        video_files = []
        
        try:
            directory_path = Path(directory)
            
            if not directory_path.exists():
                logger.warning(f"Directory does not exist: {directory}")
                return []
            
            if scan_subdirs:
                pattern = "**/*"
            else:
                pattern = "*"
            
            for file_path in directory_path.glob(pattern):
                if file_path.is_file() and file_path.suffix.lower() in video_extensions:
                    video_files.append(str(file_path))
            
            logger.info(f"Found {len(video_files)} video files in {directory}")
            
        except Exception as e:
            logger.error(f"Failed to find video files in {directory}: {e}")
        
        return sorted(video_files)
    
    async def _batch_detect_videos(self, video_paths: List[str]) -> List[MusicVideoDetectionResult]:
        """Batch detect music videos"""
        return await self.music_video_detector.batch_detect_music_videos(video_paths)
    
    async def _create_organization_action(
        self,
        video_path: str,
        detection_result: MusicVideoDetectionResult,
        target_directory: str,
        rules: OrganizationRule
    ) -> Optional[Dict[str, Any]]:
        """Create organization action for a single video"""
        try:
            source_path = Path(video_path)
            
            # Generate target path based on organization strategy
            target_path = await self._generate_target_path(
                detection_result, target_directory, rules, source_path
            )
            
            if not target_path:
                return None
            
            # Create organization action
            action = {
                'source_path': str(source_path),
                'target_path': str(target_path),
                'operation': 'move' if rules.create_artist_folders else 'rename',
                'file_size': source_path.stat().st_size if source_path.exists() else 0,
                'detection_result': detection_result.to_dict(),
                'artist': detection_result.detected_artist,
                'title': detection_result.detected_title,
                'confidence': detection_result.confidence.value,
                'video_type': detection_result.video_type.value
            }
            
            return action
            
        except Exception as e:
            logger.error(f"Failed to create organization action for {video_path}: {e}")
            return None
    
    async def _generate_target_path(
        self,
        detection_result: MusicVideoDetectionResult,
        target_directory: str,
        rules: OrganizationRule,
        source_path: Path
    ) -> Optional[Path]:
        """Generate target path based on organization rules"""
        try:
            target_base = Path(target_directory)
            
            # Get artist and title
            artist = detection_result.detected_artist or "Unknown Artist"
            title = detection_result.detected_title or source_path.stem
            
            # Sanitize names if requested
            if rules.sanitize_names:
                artist = self._sanitize_filename(artist)
                title = self._sanitize_filename(title)
            
            # Build path components based on strategy
            path_components = []
            filename_parts = []
            
            if rules.strategy == OrganizationStrategy.ARTIST_TITLE:
                path_components = [artist] if rules.create_artist_folders else []
                filename_parts = [artist, title] if not rules.create_artist_folders else [title]
                
            elif rules.strategy == OrganizationStrategy.ARTIST_ALBUM_TITLE:
                # For now, we don't have album detection, so treat like ARTIST_TITLE
                path_components = [artist] if rules.create_artist_folders else []
                filename_parts = [artist, title] if not rules.create_artist_folders else [title]
                
            elif rules.strategy == OrganizationStrategy.GENRE_ARTIST:
                genre = detection_result.detected_genres[0] if detection_result.detected_genres else "Unknown Genre"
                if rules.sanitize_names:
                    genre = self._sanitize_filename(genre)
                path_components = [genre, artist] if rules.create_artist_folders else []
                filename_parts = [genre, artist, title] if not rules.create_artist_folders else [title]
                
            elif rules.strategy == OrganizationStrategy.YEAR_ARTIST:
                # Try to extract year from filename or use current year
                year = self._extract_year(source_path.name) or datetime.now().year
                path_components = [str(year), artist] if rules.create_artist_folders else []
                filename_parts = [str(year), artist, title] if not rules.create_artist_folders else [title]
                
            elif rules.strategy == OrganizationStrategy.FLAT_ARTIST_TITLE:
                path_components = []
                filename_parts = [artist, title]
                
            elif rules.strategy == OrganizationStrategy.CUSTOM:
                if rules.custom_pattern:
                    # Simple custom pattern support - would be expanded in production
                    custom_path = rules.custom_pattern.format(
                        artist=artist,
                        title=title,
                        year=datetime.now().year
                    )
                    path_components = custom_path.split('/')[:-1]
                    filename_parts = [custom_path.split('/')[-1]]
                else:
                    # Fall back to ARTIST_TITLE
                    path_components = [artist] if rules.create_artist_folders else []
                    filename_parts = [artist, title] if not rules.create_artist_folders else [title]
            
            # Add quality indicators if requested
            if rules.preserve_quality_info:
                quality_info = self._extract_quality_info(source_path.name)
                if quality_info:
                    filename_parts.extend(quality_info)
            
            # Build filename
            filename = " - ".join(filename_parts) if len(filename_parts) > 1 else filename_parts[0]
            filename = f"{filename}{source_path.suffix}"
            
            # Ensure filename length limit
            if len(filename) > rules.max_filename_length:
                # Truncate while preserving extension
                max_name_length = rules.max_filename_length - len(source_path.suffix)
                filename = filename[:max_name_length] + source_path.suffix
            
            # Build full target path
            target_path = target_base
            for component in path_components:
                target_path = target_path / component
            target_path = target_path / filename
            
            return target_path
            
        except Exception as e:
            logger.error(f"Failed to generate target path: {e}")
            return None
    
    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for cross-platform compatibility"""
        # Remove invalid characters
        sanitized = self.invalid_chars.sub('', filename)
        
        # Collapse multiple spaces
        sanitized = self.multiple_spaces.sub(' ', sanitized)
        
        # Remove leading/trailing dots and spaces
        sanitized = self.leading_trailing_dots.sub('', sanitized.strip())
        
        # Handle reserved names
        if sanitized.upper() in self.reserved_names:
            sanitized = f"_{sanitized}"
        
        return sanitized or "Unknown"
    
    def _extract_quality_info(self, filename: str) -> List[str]:
        """Extract quality/version information from filename"""
        quality_info = []
        filename_upper = filename.upper()
        
        for indicator in self.quality_indicators:
            if indicator.upper() in filename_upper:
                quality_info.append(indicator)
        
        return quality_info
    
    def _extract_year(self, filename: str) -> Optional[int]:
        """Extract year from filename"""
        year_pattern = re.compile(r'\b(19|20)\d{2}\b')
        match = year_pattern.search(filename)
        return int(match.group()) if match else None
    
    async def _check_organization_conflict(
        self,
        action: Dict[str, Any],
        existing_actions: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Check for conflicts with existing organization actions"""
        target_path = action['target_path']
        
        # Check for duplicate target paths
        for existing_action in existing_actions:
            if existing_action['target_path'] == target_path:
                return {
                    'type': 'duplicate_target',
                    'action': action,
                    'conflict_with': existing_action,
                    'message': f"Multiple files would be moved to: {target_path}"
                }
        
        # Check if target file already exists
        if os.path.exists(target_path):
            return {
                'type': 'file_exists',
                'action': action,
                'message': f"Target file already exists: {target_path}"
            }
        
        return None
    
    async def _execute_organization_action(
        self,
        action: Dict[str, Any],
        dry_run: bool,
        created_folders: Set[str]
    ) -> Dict[str, Any]:
        """Execute a single organization action"""
        result = {
            'moved': False,
            'renamed': False,
            'folder_created': False
        }
        
        try:
            source_path = Path(action['source_path'])
            target_path = Path(action['target_path'])
            
            if not dry_run:
                # Create target directory if needed
                target_dir = target_path.parent
                if str(target_dir) not in created_folders and not target_dir.exists():
                    target_dir.mkdir(parents=True, exist_ok=True)
                    created_folders.add(str(target_dir))
                    result['folder_created'] = True
                    logger.debug(f"Created directory: {target_dir}")
                
                # Handle file conflicts
                if target_path.exists():
                    # Create unique filename
                    counter = 1
                    while target_path.exists():
                        stem = target_path.stem
                        suffix = target_path.suffix
                        new_name = f"{stem} ({counter}){suffix}"
                        target_path = target_path.parent / new_name
                        counter += 1
                
                # Move/copy the file
                shutil.move(str(source_path), str(target_path))
                result['moved'] = True
                
                logger.debug(f"Moved: {source_path} -> {target_path}")
            
            else:
                logger.info(f"DRY RUN: Would move {source_path} -> {target_path}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to execute organization action: {e}")
            raise
    
    async def get_organization_statistics(self, directory: str) -> Dict[str, Any]:
        """Get statistics about current collection organization"""
        try:
            stats = {
                'total_videos': 0,
                'organized_videos': 0,
                'unorganized_videos': 0,
                'artists_found': set(),
                'genres_found': set(),
                'organization_quality': 0.0,
                'suggestions': []
            }
            
            # This would analyze the directory structure and provide stats
            # Implementation would scan the directory and assess organization quality
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get organization statistics: {e}")
            return {}

# Global service instance
_collection_organizer_instance = None

async def get_collection_organizer(config: Optional[Dict] = None) -> CollectionOrganizer:
    """Get global collection organizer instance"""
    global _collection_organizer_instance
    
    if _collection_organizer_instance is None:
        _collection_organizer_instance = CollectionOrganizer(config)
        await _collection_organizer_instance.initialize()
    
    return _collection_organizer_instance