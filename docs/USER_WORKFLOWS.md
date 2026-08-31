# MVidarr User Workflows Guide

## Overview

This guide provides step-by-step workflows for common MVidarr tasks, helping users efficiently manage their music video library. Each workflow includes detailed instructions, screenshots references, and tips for optimal usage.

## 🚀 Getting Started Workflows

### First-Time Setup Workflow

#### Initial Configuration
1. **Access MVidarr** - Navigate to `http://localhost:5000` (or your configured URL)
2. **Authentication Setup** (if required)
   - Go to Settings → General → Authentication
   - Enable authentication if desired
   - Set username and secure password
3. **Configure File Paths**
   - Settings → General → File Paths
   - Set Downloads Path: `/path/to/downloads`
   - Set Music Videos Path: `/path/to/organized/videos`
   - Set Thumbnails Path: `/path/to/thumbnails`
4. **Add API Keys** (Essential for full functionality)
   - Settings → Services → IMVDB API Key
   - Settings → Services → YouTube API Key (optional but recommended)

#### Initial Library Setup
1. **Add Your First Artist**
   - Navigate to Artists page
   - Click "Add Artist" button
   - Enter artist name and click "Add"
   - Wait for automatic video discovery
2. **Review Discovered Videos**
   - Click on artist name to view discovered videos
   - Review suggested videos and mark as "Wanted" or "Ignored"
3. **Download Your First Videos**
   - Go to Videos page
   - Filter by Status: "Wanted"
   - Select videos to download
   - Use bulk actions to "Download Selected"

### Quick Start Workflow (Advanced Users)
1. **Bulk Artist Import** - Import multiple artists from text list
2. **API Configuration** - Set up all external service integrations
3. **Automated Discovery** - Configure scheduled discovery settings
4. **Quality Preferences** - Set video quality and file format preferences

## 🎭 Artist Management Workflows

### Adding and Managing Artists

#### Adding a Single Artist
1. **Navigate to Artists Page**
   - Click "Artists" in navigation menu
   - View current artist library
2. **Add New Artist**
   - Click "➕ Add Artist" button
   - Enter artist name exactly as it appears on music services
   - Click "Add Artist"
3. **Wait for Discovery**
   - System automatically searches IMVDB and YouTube
   - Progress shown via toast notifications
   - Discovered videos appear in artist's video list

#### Bulk Artist Import
1. **Prepare Artist List**
   - Create text file with one artist name per line
   - Ensure names are accurate and properly spelled
2. **Import Process**
   - Artists page → "Bulk Actions" → "Import Artists"
   - Upload text file or paste artist names
   - Click "Import All"
   - Monitor progress via notifications

#### Artist Profile Management
1. **Access Artist Profile**
   - Click artist name from Artists list
   - View comprehensive artist information
2. **Update Artist Information**
   - Click "Edit Artist" button
   - Update bio, thumbnail, or metadata
   - Save changes
3. **Manual Video Discovery**
   - Click "🔍 Discover Videos" button
   - Force refresh of video search
   - Review newly discovered videos

### Artist Organization

#### Folder Structure Management
1. **Automatic Organization** (Recommended)
   - Settings → Downloads → Auto-organize downloads: ✓
   - Videos automatically sorted by artist folders
2. **Manual Organization**
   - Videos page → Select videos → Bulk Actions → "Organize Files"
   - Choose organization method (by artist, by year, etc.)

## 🎬 Video Management Workflows

### Video Discovery and Adding

#### Automatic Video Discovery
1. **Artist-Based Discovery** (Primary method)
   - Add artist → System automatically finds videos
   - Scheduled discovery finds new releases
2. **Manual Video Search**
   - Videos page → "Add Video" button
   - Search by song title and artist
   - Select from IMVDB or YouTube results
   - Add to library

#### Manual Video Addition
1. **Add by URL**
   - Copy YouTube video URL
   - Videos page → "Add Video" → "Batch Import" tab
   - Paste URL and click "Import"
2. **Add by Search**
   - Videos page → "Add Video" → "Single Video" tab
   - Enter song title and artist
   - Select from search results

### Video Status Management

#### Understanding Video Statuses
- **WANTED** - Marked for download, will be processed by scheduler
- **DOWNLOADING** - Currently being downloaded
- **DOWNLOADED** - Successfully downloaded and organized
- **FAILED** - Download failed, requires attention
- **IGNORED** - Marked to skip, won't be downloaded

#### Status Workflow
1. **Review New Videos**
   - Filter videos by Status: "New" or "Discovered"
   - Review each video for relevance and quality
2. **Mark Videos as Wanted**
   - Select relevant videos
   - Bulk Actions → "Mark as Wanted"
3. **Download Management**
   - Wanted videos automatically queued for download
   - Monitor progress in Downloads section
4. **Handle Failed Downloads**
   - Filter by Status: "Failed"
   - Click "Retry Download" or investigate error

### Bulk Video Operations

#### Bulk Selection Methods
1. **Manual Selection** - Check individual video boxes
2. **Filter-Based Selection** - Use filters then "Select All"
3. **Status-Based Selection** - Bulk Actions → "Select by Status"
4. **Artist-Based Selection** - Bulk Actions → "Select by Artist"

#### Common Bulk Operations
1. **Bulk Download**
   - Select wanted videos → "Download Selected"
   - Monitor progress via notifications
2. **Bulk Status Change**
   - Select videos → Choose status → "Apply"
3. **Bulk Quality Upgrade**
   - Select videos → "Upgrade Quality"
   - System finds higher quality versions

## 📥 Download Management Workflows

### Download Queue Management

#### Understanding Download Queue
1. **Queue Priority**
   - Manual downloads: Highest priority
   - Scheduled downloads: Medium priority
   - Background discovery: Lowest priority
2. **Queue Monitoring**
   - Dashboard shows active downloads
   - Download progress displayed in real-time

#### Managing Active Downloads
1. **View Download Status**
   - Dashboard → "Active Downloads" section
   - Shows current download progress
2. **Pause/Resume Downloads**
   - Individual download controls
   - Global pause for maintenance
3. **Retry Failed Downloads**
   - Downloads page → Filter "Failed"
   - Select failed items → "Retry Selected"

### Download Optimization

#### Quality Management
1. **Set Quality Preferences**
   - Settings → Downloads → Video Quality
   - Options: Best, 1080p, 720p, 480p, etc.
2. **Upgrade Existing Videos**
   - Videos page → Filter by quality
   - Select lower quality videos
   - Bulk Actions → "Upgrade Quality"

#### Bandwidth Management
1. **Concurrent Downloads**
   - Settings → Downloads → Max Concurrent Downloads
   - Balance speed vs. system resources
2. **Scheduled Downloads**
   - Settings → Scheduling → Auto-Download Schedule
   - Schedule during off-peak hours

## 🔍 Search and Discovery Workflows

### Advanced Search Techniques

#### Video Search
1. **Quick Search** - Top navigation search bar
2. **Advanced Filters**
   - Videos page → "Filters" button
   - Filter by artist, year, status, quality
   - Save frequently used filter combinations
3. **Universal Search**
   - Searches across all content types
   - Keyboard shortcut: Ctrl+K (or Cmd+K)

#### Search Best Practices
1. **Artist Name Accuracy** - Use exact artist names for best results
2. **Song Title Variations** - Try different title formats
3. **Filter Combinations** - Combine multiple filters for precise results

### Discovery Optimization

#### Automated Discovery Configuration
1. **Schedule Setup**
   - Settings → Scheduling → Auto Discovery
   - Set frequency: Daily, Weekly, or Custom
   - Configure discovery time (off-peak recommended)
2. **Discovery Limits**
   - Max videos per artist per discovery session
   - Prevents overwhelming the library with duplicates

#### Manual Discovery Triggers
1. **Artist-Specific Discovery**
   - Artist profile → "Discover Videos" button
   - Useful after artist releases new content
2. **Global Discovery**
   - Settings → Discovery → "Run Discovery Now"
   - Discovers videos for all artists

## ⚙️ Settings and Customization Workflows

### Theme and UI Customization

#### Theme Selection
1. **Built-in Themes**
   - Settings → Appearance → Theme
   - Choose from available themes
2. **Custom Themes** (Advanced)
   - Settings → Themes → "Create Custom Theme"
   - Customize colors, fonts, and layout

#### UI Preferences
1. **Layout Options**
   - Grid view vs. List view for videos
   - Compact vs. Detailed artist display
2. **Accessibility Settings**
   - High contrast mode
   - Font size adjustments
   - Keyboard navigation options

### Notification Settings

#### Configure Notifications
1. **System Notifications**
   - Settings → Notifications → Enable system notifications
   - Choose notification types (downloads, errors, discoveries)
2. **Email Notifications** (if configured)
   - Download completion alerts
   - Error notifications
   - Weekly library reports

## 🔧 Maintenance Workflows

### Library Maintenance

#### Regular Maintenance Tasks
1. **Weekly Maintenance**
   - Review failed downloads
   - Check for duplicate videos
   - Verify file organization
2. **Monthly Maintenance**
   - Clean up ignored/unwanted videos
   - Review and update artist information
   - Check storage usage and cleanup if needed

#### Database Maintenance
1. **Performance Optimization**
   - Settings → Database → "Optimize Database"
   - Run during low-usage periods
2. **Cleanup Operations**
   - Remove orphaned thumbnails
   - Clean temporary files
   - Purge old download logs

### Backup and Restore

#### Creating Backups
1. **Database Backup**
   - Settings → Backup → "Create Database Backup"
   - Store backup files securely
2. **Configuration Backup**
   - Settings → Export → "Export Settings"
   - Save configuration file for disaster recovery

#### Restore Procedures
1. **Settings Restore**
   - Settings → Import → "Import Settings"
   - Upload previously exported configuration
2. **Database Restore**
   - Stop MVidarr service
   - Replace database file with backup
   - Restart service

## 📱 Mobile and Remote Access Workflows

### Mobile Usage

#### Mobile-Optimized Interface
1. **Responsive Design** - Automatically adapts to mobile screens
2. **Touch-Friendly Controls** - Optimized for touch interaction
3. **Mobile-Specific Features**
   - Swipe gestures for bulk selection
   - Pull-to-refresh for content updates

#### Mobile Best Practices
1. **Network Considerations** - Use WiFi for downloads
2. **Battery Optimization** - Limit concurrent operations
3. **Storage Management** - Monitor available space

### Remote Access Setup

#### Secure Remote Access
1. **VPN Access** (Recommended)
   - Set up VPN to home network
   - Access MVidarr through local IP
2. **Reverse Proxy** (Advanced)
   - Configure Nginx or Apache proxy
   - Set up SSL certificates
   - Configure firewall rules

## 🤝 Collaboration Workflows

### Multi-User Environments

#### User Management
1. **User Roles**
   - Admin: Full access to all features
   - Manager: Library management, no system settings
   - User: Basic library access
   - ReadOnly: View-only access
2. **User Account Management**
   - Settings → Users → "Add User"
   - Assign appropriate roles
   - Monitor user activity

#### Sharing and Collaboration
1. **Shared Libraries** - Multiple users managing same library
2. **Request System** - Users can request specific videos
3. **Activity Logging** - Track who made what changes

## 🚨 Troubleshooting Workflows

### Common Issue Resolution

#### Performance Issues
1. **Slow Loading** 
   - Check system resources
   - Restart MVidarr service
   - Clear browser cache
2. **Failed Downloads**
   - Verify internet connection
   - Check YouTube/IMVDB service status
   - Review error logs

#### Connection Issues
1. **Can't Access Interface**
   - Verify service is running
   - Check firewall settings
   - Confirm port configuration
2. **API Connection Failures**
   - Verify API keys in Settings
   - Check API service status
   - Test connection from different network

### Getting Help

#### Self-Help Resources
1. **Built-in Help** - Question mark icons throughout interface
2. **Log Analysis** - Settings → Logs → View recent errors
3. **Health Check** - Settings → System → "System Health Check"

#### Community Support
1. **Documentation** - Comprehensive docs in `/docs` directory
2. **GitHub Issues** - Report bugs and feature requests
3. **Community Forums** - User discussions and solutions

## 📈 Advanced Workflows

### Automation Setup

#### Complete Automation Workflow
1. **Initial Setup**
   - Configure all API keys
   - Set up file paths and permissions
   - Add initial artist list
2. **Automation Configuration**
   - Enable scheduled discovery
   - Configure auto-download settings
   - Set up maintenance schedules
3. **Monitoring Setup**
   - Configure notifications
   - Set up log monitoring
   - Create backup schedules

#### Power User Features
1. **API Usage** - Direct API access for custom integrations
2. **Webhook Integration** - Connect to external services
3. **Custom Scripts** - Automate complex workflows

### Integration Workflows

#### Plex Integration
1. **Setup Connection**
   - Settings → Services → Plex Server URL
   - Configure Plex token
2. **Library Sync**
   - Automatic library updates
   - Metadata synchronization

#### Music Service Integration
1. **Spotify Integration**
   - OAuth setup
   - Playlist synchronization
   - Artist following automation
2. **Last.fm Integration**
   - Scrobbling setup
   - Play history analysis

## 📋 Workflow Quick Reference

### Daily Tasks
- [ ] Check download progress
- [ ] Review newly discovered videos
- [ ] Mark relevant videos as wanted

### Weekly Tasks  
- [ ] Review and organize downloads
- [ ] Check for failed downloads and retry
- [ ] Update artist information if needed

### Monthly Tasks
- [ ] Run system health check
- [ ] Review storage usage
- [ ] Clean up unwanted/duplicate content
- [ ] Backup configuration and database

### As Needed
- [ ] Add new artists
- [ ] Configure new integrations
- [ ] Update API keys
- [ ] Adjust quality preferences

## 🔗 Related Documentation

- **Installation Guide**: `installation.md`
- **Configuration Guide**: `CONFIGURATION_GUIDE.md` 
- **Troubleshooting**: `TROUBLESHOOTING.md`
- **API Documentation**: `API_DOCUMENTATION.md`
- **User Guide**: `USER-GUIDE.md`

This workflow guide ensures efficient use of MVidarr's features while maintaining a well-organized music video library.