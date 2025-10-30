# Discogs API Setup for MVidarr

Discogs provides comprehensive music metadata including accurate release dates and album information. As of 2024, Discogs requires authentication for all API requests.

## Why Discogs?

MVidarr now prioritizes Discogs for:
- **Release dates** - More accurate than other sources
- **Album titles** - Essential for music video organization
- **Genre information** - Comprehensive genre/style metadata
- **Release details** - Country, label, format information

## Getting a Discogs API Token

### Step 1: Create a Discogs Account
1. Go to [Discogs.com](https://www.discogs.com)
2. Sign up for a free account (if you don't have one)

### Step 2: Generate Personal Access Token
1. Go to [Developer Settings](https://www.discogs.com/settings/developers)
2. Click **"Generate new token"**
3. Give it a name (e.g., "MVidarr")
4. Copy the generated token (it looks like: `AbCdEfGhIjKlMnOpQrStUvWxYz123456`)

⚠️ **Important**: Save this token securely! You won't be able to see it again.

## Configuring MVidarr with Discogs Token

### Method 1: Environment Variable (Recommended)

Add the token to your systemd service file:

```bash
# Edit the service file
sudo nano /etc/systemd/system/mvidarr.service

# Add this line in the [Service] section:
Environment="DISCOGS_TOKEN=YOUR_TOKEN_HERE"

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart mvidarr.service
```

### Method 2: Docker Environment Variable

If running in Docker, add to your docker-compose.yml:

```yaml
environment:
  - DISCOGS_TOKEN=YOUR_TOKEN_HERE
```

Or use docker run:

```bash
docker run -e DISCOGS_TOKEN=YOUR_TOKEN_HERE ...
```

## Verifying Setup

Check the logs to confirm Discogs is working:

```bash
# Check for successful authentication
journalctl -u mvidarr.service -f | grep -i discogs

# You should see:
# "Discogs integration enabled with authentication (top priority for release dates)"
```

## Testing

1. Go to any video details page
2. Click **"Enhanced Refresh Metadata"**
3. Check the logs - you should see Discogs being queried first
4. The video should now have album information populated

## Rate Limits

- **Without token**: 25 requests per minute
- **With token**: 60 requests per minute

MVidarr automatically respects these limits.

## Troubleshooting

### "401 Unauthorized" errors
- Your token is missing or invalid
- Check the environment variable is set correctly
- Verify the token at https://www.discogs.com/settings/developers

### No album information
- Some tracks may not have release information in Discogs
- Try different track/artist name variations
- Check logs for what Discogs is returning

### Rate limit errors
- MVidarr will automatically wait between requests
- For bulk operations, this is normal and expected

## Privacy Note

The Discogs token only grants read-only access to the Discogs database. It does not access your personal Discogs collection or profile information.

## Support

- Discogs API Documentation: https://www.discogs.com/developers
- MVidarr Issues: https://github.com/prefect421/mvidarr/issues
