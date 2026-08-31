# 📖 MVidarr - Complete User Guide

> **🎯 Master your music video collection with this comprehensive step-by-step guide**

This guide will take you through every aspect of MVidarr, from initial setup to advanced features. Each section includes screenshots and detailed explanations to help you get the most from your music video management system.

---

## 📋 Table of Contents

1. [🚀 First Time Setup](#-first-time-setup)
2. [🎯 Dashboard Overview](#-dashboard-overview)
3. [👨‍🎤 Artist Management](#-artist-management)
4. [📺 Video Discovery & Management](#-video-discovery--management)
5. [📥 Download Management](#-download-management)
6. [🎥 Video Streaming](#-video-streaming)
7. [🖼️ Thumbnail Management](#️-thumbnail-management)
8. [⚙️ Settings & Configuration](#️-settings--configuration)
9. [🔍 Advanced Search & Filtering](#-advanced-search--filtering)
10. [📱 Mobile Usage](#-mobile-usage)
11. [🔧 Troubleshooting](#-troubleshooting)

---

## 🚀 First Time Setup

### Initial Access
After installation, navigate to `http://localhost:5000` in your web browser.

![Initial Login](screenshots/initial-login.png)
*Initial login interface - shows the login form with username/password fields*

### Step 1: Welcome Screen
![Welcome Screen](screenshots/welcome-screen.png)
*Welcome to MVidarr - your journey begins here*

The welcome screen provides:
- **Quick start options** for immediate setup
- **Feature overview** highlighting key capabilities
- **Setup wizard** for guided configuration

### Step 2: API Configuration
![API Setup](screenshots/api-setup.png)
*API configuration section showing IMVDb and YouTube API key input fields with status indicators*

**Required Setup:**
1. **IMVDb API Key**
   - Visit https://imvdb.com/developers/api
   - Register for an account
   - Generate your API key
   - Paste it in the IMVDb API Key field

2. **YouTube API Key** (Recommended)
   - Go to https://console.developers.google.com
   - Create a new project or select existing
   - Enable YouTube Data API v3
   - Generate an API key
   - Add it to the YouTube API Key field

**Why these APIs matter:**
- **IMVDb**: Provides rich metadata, official video information, and artist details
- **YouTube**: Enables video discovery, thumbnails, and enhanced search capabilities

### Step 3: Storage Configuration
![Storage Setup](screenshots/storage-setup.png)
*Configure where your music videos and data will be stored*

**Key Settings:**
- **Music Videos Path**: Where downloaded videos are stored (e.g., `/home/user/MusicVideos`)
- **Quality Preference**: Choose default video quality (720p, 1080p, 4K)
- **Organization Structure**: How files are organized (Artist/Album/Video)

**Recommended Structure:**
```
/home/user/MusicVideos/
├── Artist Name/
│   ├── Album Name/
│   │   └── Song Name.mp4
│   └── Singles/
│       └── Single Name.mp4
```

### Step 4: Initial Theme Selection
![Theme Selection](screenshots/theme-selection-setup.png)
*Choose your preferred theme and appearance*

**Available Themes:**
- **🌙 Dark Mode**: Easy on the eyes for extended use
- **☀️ Light Mode**: Clean and bright interface
- **🎨 Color Variants**: Multiple accent color options
- **🖥️ Auto Mode**: Follows system theme preference

---

## 🎯 Dashboard Overview

### Main Dashboard
![Dashboard Main](screenshots/dashboard-main.png)
*Dashboard overview showing statistics cards, quick actions, and navigation menu*

The dashboard provides instant access to:

#### 📊 **Statistics Cards**
![Stats Cards](screenshots/stats-cards.png)
*Statistics cards showing key metrics: Artists count, Videos count, Downloads status, and Storage usage*
- **Artists**: Total tracked artists
- **Videos**: Total videos in library
- **Downloads**: Active and queued downloads
- **Storage**: Used space and available capacity

#### 🚀 **Quick Actions**
![Quick Actions](screenshots/quick-actions.png)
- **Add Artist**: Jump straight to artist addition
- **Import Videos**: Bulk import existing video files
- **System Health**: Check all components
- **Settings**: Access configuration

#### 📈 **Recent Activity**
![Recent Activity](screenshots/recent-activity.png)
- Recently added artists
- Latest video downloads
- System notifications
- Performance alerts

#### 🏥 **System Health Overview**
![System Health](screenshots/system-health-overview.png)
Real-time status of all system components:
- **Database**: Connection and performance
- **APIs**: IMVDb and YouTube connectivity
- **Storage**: Available space and write permissions
- **Downloads**: Active download processes

---

## 👨‍🎤 Artist Management

### Artist List View
![Artist List](screenshots/artist-list-view.png)
*Comprehensive view of all your tracked artists with search and filtering*

**Key Features:**
- **Search bar** with real-time filtering
- **Sort options** (Name, Date Added, Video Count)
- **Bulk selection** for mass operations
- **Quick actions** per artist

### Adding a New Artist

#### Step 1: Search for Artist
![Add Artist Search](screenshots/add-artist-search.png)
*Search for artists using the IMVDb database for accurate results*

1. Click **"Add Artist"** button
2. Enter artist name in search field
3. Select from search suggestions
4. Choose the correct match from results

**Pro Tip:** Use the official artist name for best results. For example, use "Taylor Swift" instead of variations like "TaylorSwift" or "T.Swift".

#### Step 2: Configure Monitoring
![Artist Configuration](screenshots/artist-configuration.png)
*Set up monitoring and automatic download preferences*

**Monitoring Options:**
- ✅ **Monitor New Releases**: Automatically check for new videos
- ✅ **Auto-Download Official Videos**: Download official music videos automatically  
- ✅ **Include Live Performances**: Also monitor live performances
- ✅ **Include Covers/Remixes**: Include cover versions and remixes
- ❌ **Skip Lyric Videos**: Exclude lyric videos from monitoring

**Quality Settings:**
- **Preferred Quality**: 1080p (recommended)
- **Fallback Quality**: 720p if 1080p unavailable
- **Maximum File Size**: 500MB per video

#### Step 3: Initial Video Discovery
![Initial Discovery](screenshots/initial-discovery.png)
*First-time discovery of existing videos for the artist*

After adding an artist, MVidarr will:
1. **Search IMVDb** for official artist videos
2. **Query YouTube** for additional content
3. **Display results** for your review
4. **Allow selection** of videos to add to library

### Artist Detail View
![Artist Detail](screenshots/artist-detail.png)
*Comprehensive artist information and management interface*

The artist detail page includes:

#### 🖼️ **Artist Header**
- **Artist photo/thumbnail**
- **Name and alternate names**
- **Genre information**
- **Active monitoring status**

#### 📊 **Statistics Overview**
![Artist Stats](screenshots/artist-stats.png)
- Total videos in library
- Downloaded vs. wanted videos
- Storage usage for this artist
- Last discovery date

#### 📺 **Videos Tab**
![Artist Videos](screenshots/artist-videos-tab.png)
*All videos for this artist with management options*

**Features:**
- **Video grid** with thumbnails
- **Status indicators** (Downloaded, Wanted, Failed)
- **Bulk selection** for mass operations
- **Search and filtering** within artist's videos

#### ⚙️ **Settings Tab**
![Artist Settings](screenshots/artist-settings.png)
*Configure monitoring and download preferences*

**Available Settings:**
- **Monitoring enabled/disabled**
- **Auto-download preferences**
- **Quality settings**
- **File organization options**
- **Notification preferences**

#### 🔍 **Discovery Tab**
![Artist Discovery](screenshots/artist-discovery.png)
*Manual video discovery and import*

**Discovery Features:**
- **Manual search** for new videos
- **Source selection** (IMVDb, YouTube, Both)
- **Filter options** (Official, Live, Covers, etc.)
- **Bulk import** with preview

#### 📈 **Activity Tab**
![Artist Activity](screenshots/artist-activity.png)
*Recent activity and download history*

**Activity Log:**
- Recent video additions
- Download successes/failures
- Metadata updates
- System notifications

### Bulk Artist Operations
![Bulk Operations](screenshots/bulk-artist-operations.png)
*Efficiently manage multiple artists at once*

**Available Bulk Operations:**
1. **Enable/Disable Monitoring**: Toggle monitoring for selected artists
2. **Update Metadata**: Refresh information from IMVDb
3. **Discovery Search**: Search for new videos for all selected artists
4. **Quality Settings**: Apply quality preferences to multiple artists
5. **Delete Artists**: Remove artists and optionally their videos

**How to Use Bulk Operations:**
1. Select multiple artists using checkboxes
2. Click **"Actions"** dropdown in the toolbar
3. Choose desired operation
4. Configure operation parameters
5. Confirm and execute

---

## 📺 Video Discovery & Management

### Video Library Overview
![Video Library](screenshots/video-library-overview.png)
*Your complete music video collection with powerful management tools*

The video library provides:
- **Grid/List view** toggle for different browsing experiences
- **Advanced filtering** by status, genre, quality, and more
- **Bulk selection** for mass operations
- **Real-time search** with instant results

### Video Discovery Process

#### Automatic Discovery
![Auto Discovery](screenshots/auto-discovery.png)
*Automatic discovery runs in the background for monitored artists*

**When Discovery Runs:**
- **New artist added**: Immediate discovery of existing catalog
- **Scheduled intervals**: Daily/weekly checks for new releases
- **Manual triggers**: User-initiated discovery runs
- **After metadata updates**: Re-discovery following artist updates

#### Manual Discovery
![Manual Discovery](screenshots/manual-discovery.png)
*Manually discover videos with full control over sources and filters*

**Manual Discovery Steps:**
1. **Select Artist(s)**: Choose specific artists or search all
2. **Choose Sources**: IMVDb, YouTube, or both
3. **Set Filters**: Official videos, live performances, covers, etc.
4. **Run Discovery**: Execute search with selected parameters
5. **Review Results**: Preview discovered videos before adding

#### Discovery Results
![Discovery Results](screenshots/discovery-results.png)
*Review and select videos from discovery results*

**Result Information:**
- **Thumbnail preview** with play button
- **Video title and artist**
- **Source indicator** (IMVDb/YouTube)
- **Duration and quality**
- **Release date and view count**

**Selection Options:**
- **Individual selection** with checkboxes
- **Select all official videos** quick action
- **Filter by type** (Official, Live, Covers)
- **Bulk import** selected videos

### Video Management Interface

#### Video Card View
![Video Cards](screenshots/video-cards.png)
*Rich video cards with thumbnails and metadata*

**Card Information:**
- **Thumbnail** with quality indicator
- **Title** and artist name
- **Duration** and file size
- **Status badges** (Downloaded, Wanted, Failed)
- **Quick actions** (Play, Download, More)

#### Video List View
![Video List](screenshots/video-list.png)
*Detailed list view with sortable columns*

**List Columns:**
- **Thumbnail**: Visual preview
- **Title**: Video name with artist
- **Status**: Current download/availability status
- **Quality**: Resolution and format
- **Size**: File size (if downloaded)
- **Date Added**: When video was discovered
- **Actions**: Quick action buttons

#### Video Detail Modal
![Video Detail](screenshots/video-detail.png)
*Comprehensive video information and management*

**Detail Sections:**
1. **Basic Information**
   - Title, artist, and alternate titles
   - Duration, quality, and file format
   - Release date and view count

2. **Metadata**
   - Genre and tags
   - Directors and producers
   - Album association
   - Description and notes

3. **Files**
   - Download status and location
   - File size and quality options
   - Thumbnail variants

4. **Actions**
   - Download/re-download options
   - Edit metadata
   - Delete video
   - Search for alternatives

### Video Status Management

#### Status Indicators
![Status Indicators](screenshots/status-indicators.png)
*Understanding video status badges and their meanings*

**Status Types:**
- **🟢 Downloaded**: Video file available locally
- **🟡 Wanted**: Marked for download, queued or waiting
- **🔴 Failed**: Download failed, needs attention
- **⚪ Skipped**: Intentionally not downloaded
- **🔵 Upgrading**: Better quality version downloading

#### Changing Video Status
![Status Management](screenshots/status-management.png)
*Easily change video status and download preferences*

**Status Change Options:**
- **Mark as Wanted**: Queue for download
- **Mark as Skipped**: Don't download this video
- **Force Re-download**: Download again (quality upgrade)
- **Search Alternatives**: Find different versions

### Bulk Video Operations
![Bulk Video Ops](screenshots/bulk-video-operations.png)
*Efficiently manage multiple videos simultaneously*

**Available Bulk Operations:**
1. **Download Selected**: Queue multiple videos for download
2. **Mark as Wanted/Skipped**: Change status for multiple videos
3. **Update Metadata**: Refresh information from sources
4. **Delete Videos**: Remove videos from library (with file options)
5. **Quality Upgrade**: Search for better quality versions
6. **Organize Files**: Move/rename video files

**Bulk Operation Workflow:**
1. **Filter videos** to show desired subset
2. **Select videos** using checkboxes or "Select All"
3. **Choose operation** from Actions dropdown
4. **Configure parameters** for the operation
5. **Review selection** in confirmation dialog
6. **Execute operation** and monitor progress

---

## 📥 Download Management

### Download Queue Overview
![Download Queue](screenshots/download-queue.png)
*Monitor and manage all video downloads in real-time*

The download manager provides:
- **Real-time progress** for active downloads
- **Queue management** with priority settings
- **Detailed logging** of download attempts
- **Error handling** and retry mechanisms

### Download Process

#### Queue Management
![Queue Management](screenshots/queue-management.png)
*Control download order and priorities*

**Queue Features:**
- **Drag-and-drop reordering** of queued downloads
- **Priority settings** (High, Normal, Low)
- **Pause/Resume** individual downloads
- **Cancel downloads** with cleanup options

#### Active Downloads
![Active Downloads](screenshots/active-downloads.png)
*Real-time monitoring of downloading videos*

**Download Information:**
- **Progress bar** with percentage complete
- **Download speed** and time remaining
- **File size** (current/total)
- **Source URL** and quality being downloaded
- **Error messages** if issues occur

#### Download History
![Download History](screenshots/download-history.png)
*Complete history of all download attempts*

**History Details:**
- **Success/failure status** for each attempt
- **Download timestamps** (started/completed)
- **File information** (size, quality, format)
- **Error logs** for troubleshooting failed downloads
- **Retry options** for failed downloads

### Download Configuration

#### Global Download Settings
![Download Settings](screenshots/download-settings-global.png)
*Configure system-wide download preferences*

**Key Settings:**
- **Concurrent Downloads**: How many videos to download simultaneously (recommended: 2-3)
- **Download Speed Limit**: Bandwidth throttling (optional)
- **Retry Attempts**: How many times to retry failed downloads
- **Quality Preferences**: Default quality selection order
- **File Organization**: Automatic file naming and folder structure

#### Per-Artist Download Settings
![Per-Artist Downloads](screenshots/per-artist-download-settings.png)
*Customize download behavior for specific artists*

**Artist-Specific Options:**
- **Quality Override**: Use different quality for this artist
- **Auto-Download**: Enable/disable automatic downloading
- **File Naming**: Custom naming template for this artist
- **Organization**: Different folder structure for this artist

### Download Troubleshooting

#### Common Download Issues
![Download Issues](screenshots/download-issues.png)
*Identify and resolve common download problems*

**Issue Types:**
1. **Network Errors**: Connection timeouts, DNS issues
2. **Source Unavailable**: Video removed or geoblocked
3. **Quality Not Available**: Requested quality doesn't exist
4. **Disk Space**: Insufficient storage space
5. **Permissions**: File system permission problems

#### Download Error Resolution
![Error Resolution](screenshots/error-resolution.png)
*Step-by-step guide to resolving download failures*

**Resolution Steps:**
1. **Check Error Details**: View full error message in download history
2. **Verify Source**: Manually check if video still exists at source
3. **Try Different Quality**: Attempt download with lower quality
4. **Clear Cache**: Reset download cache and temporary files
5. **Manual Download**: Use external tool if needed
6. **Report Issue**: Submit bug report for persistent issues

---

## 🎥 Video Streaming

### Built-in Video Player
![Video Player](screenshots/video-player.png)
*Professional video player with advanced features*

**Player Features:**
- **Full-screen support** with cinematic mode
- **Quality selection** (if multiple versions available)
- **Playback speed control** (0.5x to 2x)
- **Subtitle support** (if available)
- **Progress saving** and resume functionality

### Playback Controls
![Player Controls](screenshots/player-controls.png)
*Comprehensive playback controls for optimal viewing experience*

**Control Features:**
- **Play/Pause**: Space bar or click
- **Seek**: Click timeline or use arrow keys
- **Volume**: Mouse wheel or dedicated controls
- **Full-screen**: F key or double-click
- **Quality**: Right-click for quality menu

### MvTV Continuous Player
![MvTV Mode](screenshots/mvtv-mode.png)
*Continuous music video playback with playlist management*

**MvTV Features:**
- **Automatic next video**: Seamless transitions between videos
- **Playlist management**: Create and manage viewing queues
- **Artist focus**: Play all videos from specific artists
- **Genre filtering**: Continuous play by genre
- **Shuffle mode**: Random video selection

#### Creating Playlists
![Playlist Creation](screenshots/playlist-creation.png)
*Build custom playlists for continuous viewing*

**Playlist Options:**
1. **Manual Selection**: Choose specific videos
2. **Artist-Based**: All videos from selected artists
3. **Genre-Based**: Videos matching genre criteria
4. **Smart Playlists**: Dynamic based on rules (new videos, favorites, etc.)

#### Playlist Management
![Playlist Management](screenshots/playlist-management.png)
*Organize and control your video playlists*

**Management Features:**
- **Drag-and-drop reordering** of playlist items
- **Save playlists** for future use
- **Share playlists** (export/import)
- **Auto-update** smart playlists with new content

### Viewing History
![Viewing History](screenshots/viewing-history.png)
*Track your viewing activity and resume where you left off*

**History Features:**
- **Recently watched** videos with timestamps
- **Resume points** for partially watched videos
- **View count** and total watch time statistics
- **Clear history** options for privacy

---

## 🖼️ Thumbnail Management

### Thumbnail Overview
![Thumbnail Overview](screenshots/thumbnail-overview.png)
*Beautiful, high-quality thumbnails from multiple sources*

MVidarr automatically manages thumbnails from:
- **IMVDb**: Official music video artwork
- **YouTube**: Video thumbnails and channel art
- **Wikipedia**: Artist photos and album covers
- **Manual Upload**: Your own custom images

### Automatic Thumbnail Discovery
![Auto Thumbnails](screenshots/auto-thumbnails.png)
*Automatic thumbnail discovery and optimization*

**Discovery Process:**
1. **Primary Source**: IMVDb official artwork (highest quality)
2. **Secondary Source**: YouTube thumbnail (good quality)
3. **Fallback**: Wikipedia artist image (backup option)
4. **Optimization**: Automatic WebP conversion for smaller file sizes

### Manual Thumbnail Management

#### Thumbnail Search
![Thumbnail Search](screenshots/thumbnail-search.png)
*Search for better thumbnails from multiple sources*

**Search Features:**
- **Multi-source search**: Query IMVDb, YouTube, Wikipedia simultaneously
- **Quality filtering**: Show only high-resolution images
- **Relevance sorting**: Best matches first
- **Preview mode**: See images before selecting

#### Custom Thumbnail Upload
![Custom Upload](screenshots/custom-thumbnail-upload.png)
*Upload your own custom thumbnails*

**Upload Options:**
1. **Drag and Drop**: Simply drag image files into the interface
2. **File Browser**: Traditional file selection dialog
3. **URL Import**: Import directly from image URLs
4. **Cropping Tool**: Automatic cropping to optimal dimensions

#### Thumbnail Editor
![Thumbnail Editor](screenshots/thumbnail-editor.png)
*Edit and optimize thumbnails*

**Editing Features:**
- **Crop and resize**: Adjust dimensions and aspect ratio
- **Quality adjustment**: Balance file size and image quality
- **Format conversion**: Convert between JPEG, PNG, WebP
- **Multiple sizes**: Generate small, medium, large variants automatically

### Thumbnail Library
![Thumbnail Library](screenshots/thumbnail-library.png)
*Manage your complete thumbnail collection*

**Library Features:**
- **Grid view** of all thumbnails with metadata
- **Search and filter** by source, size, quality
- **Bulk operations** for multiple thumbnails
- **Storage statistics** and optimization recommendations

### Thumbnail Troubleshooting

#### Missing Thumbnails
![Missing Thumbnails](screenshots/missing-thumbnails-fix.png)
*Identify and fix missing thumbnail issues*

**Common Causes:**
- **Source unavailable**: Original image no longer exists
- **Network issues**: Temporary download failures
- **Storage problems**: Disk space or permission issues
- **Format issues**: Unsupported image formats

**Resolution Steps:**
1. **Automatic retry**: System will retry failed downloads
2. **Manual search**: Use thumbnail search to find alternatives
3. **Upload custom**: Add your own image as backup
4. **Regenerate cache**: Clear and rebuild thumbnail cache

---

## ⚙️ Settings & Configuration

### Settings Overview
![Settings Overview](screenshots/settings-main.png)
*Comprehensive configuration options organized by category*

The settings interface provides:
- **Categorized tabs** for easy navigation
- **Real-time validation** of configuration changes
- **Import/Export** settings for backup and migration
- **Reset options** to restore defaults

### External Services Configuration

#### API Keys Setup
![API Keys](screenshots/api-keys-setup.png)
*Configure your external service API credentials*

**Required APIs:**
1. **IMVDb API Key**
   - **Purpose**: Video metadata, artist information, official video discovery
   - **How to get**: Register at https://imvdb.com/developers/api
   - **Rate Limits**: 1000 requests/day (free tier)
   - **Status Check**: Green = working, Red = invalid/expired

2. **YouTube Data API v3**
   - **Purpose**: Video discovery, thumbnails, metadata enhancement
   - **How to get**: Google Cloud Console → Enable YouTube Data API → Create credentials
   - **Rate Limits**: 10,000 quota units/day (free tier)
   - **Status Check**: Automatic validation with test query

#### Service Health Monitoring
![Service Health](screenshots/service-health.png)
*Monitor the health and status of all external services*

**Health Indicators:**
- **🟢 Healthy**: Service responding normally
- **🟡 Degraded**: Slower than normal but functional
- **🔴 Failed**: Service unavailable or returning errors
- **⚪ Disabled**: Service intentionally disabled

### Download & Storage Configuration

#### Storage Settings
![Storage Settings](screenshots/storage-settings.png)
*Configure where and how your files are stored*

**Storage Configuration:**
- **Music Videos Path**: Primary storage location
- **Thumbnail Cache**: Where thumbnails are stored
- **Temporary Downloads**: Staging area for downloads
- **Database Location**: Database file storage
- **Log Files**: Application log storage location

**Storage Monitoring:**
- **Available Space**: Real-time disk space monitoring
- **Usage Statistics**: Breakdown by content type
- **Cleanup Options**: Automatic cleanup of temporary files
- **Backup Recommendations**: Suggested backup strategies

#### Download Preferences
![Download Preferences](screenshots/download-preferences.png)
*Fine-tune download behavior and quality preferences*

**Quality Settings:**
- **Preferred Quality**: First choice (1080p recommended)
- **Fallback Quality**: If preferred unavailable (720p)
- **Minimum Quality**: Lowest acceptable (480p)
- **Maximum File Size**: Per-video size limit (500MB default)

**Download Behavior:**
- **Concurrent Downloads**: Simultaneous downloads (2-3 recommended)
- **Retry Attempts**: Failed download retries (3 default)
- **Speed Limiting**: Bandwidth throttling (optional)
- **Scheduled Downloads**: Off-peak download times

#### File Organization
![File Organization](screenshots/file-organization.png)
*Customize how your video files are organized*

**Naming Templates:**
```
Default: {Artist}/{Album}/{Title}.{ext}
Examples:
- Taylor Swift/1989/Shake It Off.mp4
- The Beatles/Abbey Road/Come Together.mp4
- Various Artists/Singles/Song Title.mp4
```

**Organization Options:**
- **Create Artist Folders**: Group by artist (recommended)
- **Create Album Folders**: Sub-organize by album
- **Handle Various Artists**: Special handling for compilations
- **Sanitize Filenames**: Remove problematic characters
- **Duplicate Handling**: What to do with duplicates

### User Interface Configuration

#### Theme & Appearance
![Theme Settings](screenshots/theme-settings.png)
*Customize the look and feel of your interface*

**Theme Options:**
- **Dark Mode**: Easy on eyes, great for extended use
- **Light Mode**: Clean and bright appearance
- **Auto Mode**: Follow system preference
- **Color Accent**: Choose from 10+ accent colors
- **Compact Mode**: Denser layout for smaller screens

#### Display Preferences
![Display Preferences](screenshots/display-preferences.png)
*Configure how information is displayed*

**Layout Options:**
- **Items per Page**: Pagination size (25, 50, 100)
- **Card Size**: Thumbnail size in grid views
- **List Density**: Compact or comfortable list spacing
- **Show Tooltips**: Helpful hints and explanations
- **Animation Level**: Full, reduced, or disabled animations

#### Language & Region
![Language Settings](screenshots/language-settings.png)
*Localization and regional preferences*

**Regional Settings:**
- **Language**: Interface language (English default)
- **Date Format**: MM/DD/YYYY or DD/MM/YYYY
- **Time Format**: 12-hour or 24-hour clock
- **Timezone**: For accurate scheduling and logging
- **Number Format**: Decimal and thousands separators

### System Configuration

#### Database Settings
![Database Settings](screenshots/database-settings.png)
*Database connection and performance configuration*

**Connection Settings:**
- **Host**: Database server (localhost for Docker)
- **Port**: Database port (3306 default)
- **Database Name**: Database name (mvidarr)
- **Username/Password**: Authentication credentials
- **Connection Pool**: Performance tuning options

**Performance Tuning:**
- **Query Cache**: Enable/disable query result caching
- **Connection Timeout**: How long to wait for connections
- **Retry Logic**: Connection failure handling
- **Backup Schedule**: Automated database backups

#### Security Settings
![Security Settings](screenshots/security-settings.png)
*Configure security and authentication options*

**Security Options:**
- **Session Timeout**: Automatic logout time
- **Strong Passwords**: Enforce password complexity
- **Two-Factor Auth**: Enable 2FA (if configured)
- **API Access**: Enable/disable API endpoints
- **HTTPS Only**: Force secure connections

#### Logging & Debugging
![Logging Settings](screenshots/logging-settings.png)
*Configure application logging and debugging*

**Log Levels:**
- **ERROR**: Only errors and critical issues
- **WARNING**: Errors and warnings
- **INFO**: General information (recommended)
- **DEBUG**: Detailed debugging information (development)

**Log Management:**
- **Log Rotation**: Automatic cleanup of old logs
- **Max Log Size**: Individual log file size limit
- **Retention Period**: How long to keep logs
- **Export Logs**: Download logs for troubleshooting

### Backup & Recovery
![Backup Settings](screenshots/backup-settings.png)
*Configure automatic backups and recovery options*

**Backup Configuration:**
- **Automatic Backups**: Enable scheduled backups
- **Backup Frequency**: Daily, weekly, or monthly
- **Backup Location**: Where to store backup files
- **Retention Policy**: How many backups to keep
- **Include Files**: Backup video files or just metadata

---

## 🔍 Advanced Search & Filtering

### Search Interface
![Advanced Search](screenshots/advanced-search-interface.png)
*Powerful search interface with multiple criteria and real-time results*

The advanced search provides:
- **Real-time suggestions** as you type
- **Multi-field search** across all metadata
- **Saved searches** for frequently used queries
- **Search history** to revisit previous searches

### Search Criteria

#### Basic Search
![Basic Search](screenshots/basic-search.png)
*Simple text search across all content*

**Search Scope:**
- **Artist Names**: Primary and alternate names
- **Video Titles**: Original and alternate titles
- **Album Names**: Associated album information
- **Genres**: Musical genres and categories
- **Tags**: User-defined and system tags

#### Advanced Filters
![Advanced Filters](screenshots/advanced-filters.png)
*Detailed filtering options for precise results*

**Filter Categories:**

1. **Status Filters**
   - Downloaded videos only
   - Wanted videos only
   - Failed downloads
   - Recently added
   - Never downloaded

2. **Quality Filters**
   - 4K/2160p videos
   - 1080p HD videos
   - 720p HD videos
   - SD quality videos
   - Audio-only content

3. **Date Filters**
   - Release date range
   - Date added to library
   - Last download attempt
   - Last watched

4. **Source Filters**
   - IMVDb sourced videos
   - YouTube sourced videos
   - Manually added content
   - Imported from files

5. **Content Type Filters**
   - Official music videos
   - Live performances
   - Lyric videos
   - Cover versions
   - Behind-the-scenes

#### Smart Filters
![Smart Filters](screenshots/smart-filters.png)
*Intelligent filtering based on user behavior and preferences*

**Smart Filter Types:**
- **Recently Popular**: Based on view counts and trends
- **Recommended**: Based on your viewing history
- **Similar Artists**: Artists similar to those you follow
- **Missing Videos**: Videos that should exist but aren't found
- **Quality Upgrades**: Videos with better quality available

### Search Results

#### Results Display
![Search Results](screenshots/search-results-display.png)
*Flexible display options for search results*

**Display Options:**
- **Grid View**: Thumbnail grid with minimal text
- **List View**: Detailed list with metadata columns
- **Card View**: Rich cards with full information
- **Compact View**: Maximum density for large result sets

#### Result Sorting
![Result Sorting](screenshots/result-sorting.png)
*Sort search results by various criteria*

**Sorting Options:**
- **Relevance**: Best match for search terms (default)
- **Date Added**: Newest or oldest first
- **Artist Name**: Alphabetical by artist
- **Video Title**: Alphabetical by title
- **Video Duration**: Longest or shortest first
- **File Size**: Largest or smallest files
- **Quality**: Highest or lowest quality first
- **View Count**: Most or least watched

### Saved Searches
![Saved Searches](screenshots/saved-searches.png)
*Save and manage frequently used search queries*

**Saved Search Features:**
- **Quick Access**: One-click execution of saved searches
- **Auto-Update**: Searches automatically update with new content
- **Sharing**: Export/import saved searches
- **Notifications**: Alert when saved searches have new results

**Example Saved Searches:**
- "Recent Official Videos" → Status: Wanted, Type: Official, Date: Last 30 days
- "4K Quality Upgrades" → Quality: 4K, Status: Not Downloaded
- "Live Performances" → Type: Live, Artist: [Your Favorites]

### Search Analytics
![Search Analytics](screenshots/search-analytics.png)
*Understand your search patterns and optimize your workflow*

**Analytics Data:**
- **Most Searched Terms**: What you search for most often
- **Search Success Rate**: How often searches return results
- **Popular Filters**: Your most-used filter combinations
- **Time-based Patterns**: When you search most often
- **Result Click Patterns**: Which results you actually use

---

## 📱 Mobile Usage

### Mobile-Optimized Interface
![Mobile Overview](screenshots/mobile-overview.png)
*Full-featured mobile experience optimized for touch interfaces*

MVidarr provides a complete mobile experience:
- **Touch-optimized controls** for easy navigation
- **Responsive design** that adapts to any screen size
- **Swipe gestures** for intuitive interaction
- **Offline capabilities** for browsing your library

### Mobile Navigation
![Mobile Navigation](screenshots/mobile-navigation.png)
*Intuitive navigation designed for mobile use*

**Navigation Features:**
- **Hamburger menu** for main navigation
- **Bottom tab bar** for quick access to key sections
- **Pull-to-refresh** for updating content
- **Swipe gestures** for forward/back navigation

### Mobile Video Playback
![Mobile Video Player](screenshots/mobile-video-player.png)
*Full-featured video player optimized for mobile devices*

**Mobile Player Features:**
- **Full-screen playback** with automatic rotation
- **Touch controls** with overlay interface
- **Gesture controls**: Swipe for seek, pinch for zoom
- **Background audio** playback support
- **Picture-in-picture** mode (where supported)

**Mobile Playback Controls:**
- **Tap to play/pause**
- **Double-tap to seek** (10 seconds forward/back)
- **Swipe up/down** for volume control
- **Swipe left/right** for seeking
- **Pinch to zoom** in full-screen mode

### Mobile-Specific Features

#### Offline Mode
![Mobile Offline](screenshots/mobile-offline.png)
*Browse your library even without internet connection*

**Offline Capabilities:**
- **Browse downloaded videos** without internet
- **View metadata** cached locally
- **Queue downloads** for when connection returns
- **Sync when connected** to update library

#### Touch Gestures
![Mobile Gestures](screenshots/mobile-gestures.png)
*Intuitive touch gestures for efficient navigation*

**Gesture Controls:**
- **Swipe right**: Go back in navigation
- **Swipe left**: Forward in navigation (where applicable)
- **Pull down**: Refresh current page
- **Long press**: Context menu for items
- **Pinch**: Zoom in video player

#### Mobile Settings
![Mobile Settings](screenshots/mobile-settings.png)
*Mobile-specific configuration options*

**Mobile-Specific Settings:**
- **Data Usage**: Limit downloads on cellular
- **Battery Optimization**: Reduce animations and effects
- **Notification Settings**: Control push notifications
- **Gesture Sensitivity**: Adjust touch response
- **Screen Timeout**: Prevent screen sleep during playback

---

## 🔧 Troubleshooting

### Common Issues & Solutions

#### Installation Issues
![Installation Troubleshooting](screenshots/troubleshoot-installation.png)
*Resolve common installation and setup problems*

**Docker Installation Issues:**
1. **Permission Errors**
   ```bash
   # Fix: Set correct ownership for data directories
   sudo chown -R 1001:1001 /path/to/your/musicvideos
   sudo chown -R 1001:1001 /path/to/your/database
   ```

2. **Port Already in Use**
   ```bash
   # Fix: Change port in docker-config.yml
   MVIDARR_PORT=5001  # Instead of default 5000
   ```

3. **Container Won't Start**
   ```bash
   # Check logs for specific error
   docker-compose logs mvidarr
   
   # Common solutions:
   # - Verify all required directories exist
   # - Check docker-config.yml syntax
   # - Ensure sufficient disk space
   ```

**Local Installation Issues:**
1. **Python Version Conflicts**
   ```bash
   # Ensure Python 3.12+ is installed
   python3 --version
   
   # Use virtual environment
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Database Connection Failed**
   ```sql
   -- Verify database exists
   SHOW DATABASES;
   
   -- Check user permissions
   SHOW GRANTS FOR 'mvidarr'@'localhost';
   ```

#### API Connection Issues
![API Troubleshooting](screenshots/troubleshoot-api.png)
*Diagnose and fix API connectivity problems*

**IMVDb API Issues:**
1. **Invalid API Key**
   - Verify key at https://imvdb.com/developers/api
   - Check for extra spaces or characters
   - Ensure key has not expired

2. **Rate Limiting**
   - Free tier: 1000 requests/day
   - Spread operations over time
   - Consider API key upgrade if needed

**YouTube API Issues:**
1. **Quota Exceeded**
   - Check quota usage in Google Cloud Console
   - Enable billing for higher limits
   - Optimize queries to reduce quota usage

2. **API Not Enabled**
   - Enable YouTube Data API v3 in Google Cloud Console
   - Wait 5-10 minutes for activation
   - Verify project has correct API key

#### Download Issues
![Download Troubleshooting](screenshots/troubleshoot-downloads.png)
*Resolve video download problems*

**Common Download Problems:**
1. **Downloads Stuck**
   - Check internet connection
   - Verify yt-dlp is updated
   - Restart download service
   - Clear download cache

2. **Permission Denied**
   ```bash
   # Fix directory permissions
   chmod 755 /path/to/musicvideos
   chown -R user:user /path/to/musicvideos
   ```

3. **Video Unavailable**
   - Video may be region-blocked
   - Video may have been removed
   - Try alternative sources
   - Check video URL manually

4. **Quality Not Available**
   - Requested quality doesn't exist
   - Try lower quality setting
   - Check available formats manually

#### Performance Issues
![Performance Troubleshooting](screenshots/troubleshoot-performance.png)
*Optimize system performance for large libraries*

**Slow Interface:**
1. **Database Optimization**
   ```sql
   -- Optimize database tables
   OPTIMIZE TABLE artists, videos, downloads;
   
   -- Update statistics
   ANALYZE TABLE artists, videos, downloads;
   ```

2. **Clear Caches**
   ```bash
   # Clear thumbnail cache
   rm -rf /path/to/thumbnails/cache/
   
   # Clear application cache
   rm -rf /path/to/cache/
   ```

3. **Reduce Resource Usage**
   - Lower concurrent downloads
   - Disable animations in settings
   - Increase database buffer size
   - Close unused browser tabs

**Large Library Performance:**
- Enable pagination for all views
- Use more specific search terms
- Regular database maintenance
- Consider hardware upgrades

### Diagnostic Tools

#### Built-in System Health
![System Health Diagnostic](screenshots/system-health-diagnostic.png)
*Comprehensive system health monitoring and diagnostics*

**Health Check Categories:**
1. **Database Health**
   - Connection status
   - Query performance
   - Storage usage
   - Index optimization

2. **API Health**
   - Service connectivity
   - Rate limit status
   - Authentication validity
   - Response times

3. **Storage Health**
   - Disk space availability
   - Directory permissions
   - File system health
   - Backup status

4. **Download Health**
   - Service status
   - Queue length
   - Recent failures
   - Network connectivity

#### Log Analysis
![Log Analysis](screenshots/log-analysis.png)
*Analyze application logs to identify and resolve issues*

**Log Locations:**
- **Docker**: `docker-compose logs mvidarr`
- **Local**: `data/logs/mvidarr.log`
- **Web Interface**: Settings → System → View Logs

**Log Levels:**
- **ERROR**: Critical issues requiring attention
- **WARNING**: Potential problems or degraded performance
- **INFO**: Normal operation information
- **DEBUG**: Detailed debugging information

**Common Log Patterns:**
```
ERROR: Database connection failed → Check database settings
WARNING: API rate limit approaching → Reduce API calls
INFO: Video download completed → Normal operation
DEBUG: Cache miss for thumbnail → Performance info
```

#### Performance Monitoring
![Performance Monitoring](screenshots/performance-monitoring.png)
*Monitor system performance and identify bottlenecks*

**Performance Metrics:**
- **Response Times**: API endpoint performance
- **Memory Usage**: RAM consumption patterns
- **CPU Usage**: Processing load analysis
- **Disk I/O**: Storage access patterns
- **Network Usage**: Bandwidth consumption

**Performance Alerts:**
- Response times > 2 seconds
- Memory usage > 80%
- Disk space < 1GB available
- Failed downloads > 10%

### Getting Additional Help
![Support Resources](screenshots/support-resources-detailed.png)
*Comprehensive support resources and community assistance*

**Support Channels:**
1. **Built-in Help**
   - Tooltips and help text throughout interface
   - Settings → Help & Support
   - System health diagnostics

2. **Documentation**
   - Complete user guide (this document)
   - API documentation
   - Installation guides
   - Troubleshooting guides

3. **Community Support**
   - GitHub Issues for bug reports
   - GitHub Discussions for questions
   - Community wiki for tips and tricks

4. **Self-Help Tools**
   - System health checker
   - Log analyzer
   - Configuration validator
   - Performance optimizer

**Before Seeking Help:**
1. Check system health dashboard
2. Review recent logs for errors
3. Try basic troubleshooting steps
4. Search existing GitHub issues
5. Gather system information and logs

---

## 🎉 Conclusion

Congratulations! You've mastered MVidarr. This comprehensive guide has covered:

- ✅ **Initial setup and configuration**
- ✅ **Artist and video management**
- ✅ **Download and streaming features**
- ✅ **Advanced search and filtering**
- ✅ **Mobile usage and optimization**
- ✅ **Troubleshooting and support**

### 🚀 Next Steps

1. **Explore Advanced Features**
   - Set up automated artist monitoring
   - Create custom playlists in MvTV
   - Configure advanced download rules

2. **Optimize Your Setup**
   - Fine-tune quality preferences
   - Set up automated backups
   - Monitor system performance

3. **Join the Community**
   - Share your experience
   - Contribute improvements
   - Help other users

### 📚 Additional Resources

- **[Docker Quick Start Guide](../DOCKER-QUICKSTART.md)**: Fast deployment
- **[API Documentation](API-DOCUMENTATION.md)**: Developer integration
- **[Administrator Guide](ADMIN-GUIDE.md)**: Advanced configuration

---

*Thank you for using MVidarr! We hope this guide helps you build and manage the perfect music video collection.*

**🎵 Happy music video collecting! 🎵**