# Lyrics Integration - Removed

## Current Status

**Lyrics functionality has been removed from MVidarr** as of October 23, 2025.

The lyrics.ovh API was unreachable and deprecated. After evaluating alternatives including ChartLyrics, Genius API, and Spotify-based solutions, it was determined that lyrics integration added unnecessary complexity without sufficient value for a music video management application.

This document is kept for historical reference only.

## Short-Term Solution: Manual Entry

A new endpoint has been added for manual lyrics entry:

```
PUT /api/videos/{video_id}/lyrics?lyrics=<lyrics_text>
```

Users can manually add lyrics through the web interface or API.

## Alternative Lyrics API Services

If you want to restore automatic lyrics search, here are legitimate API alternatives:

### 1. Genius API (Recommended)
- **Website**: https://genius.com/api-clients
- **Pricing**: Free tier available (requires registration)
- **Features**: Comprehensive lyrics database, song annotations, artist info
- **Rate Limits**: Generous for personal use
- **Setup**:
  1. Create account at https://genius.com
  2. Register for API client
  3. Get API token
  4. Add to MVidarr settings

**Example Request**:
```python
import requests

headers = {'Authorization': 'Bearer YOUR_ACCESS_TOKEN'}
search_url = 'https://api.genius.com/search'
params = {'q': f'{artist} {song_title}'}
response = requests.get(search_url, headers=headers, params=params)
```

### 2. Musixmatch API
- **Website**: https://developer.musixmatch.com/
- **Pricing**: Free tier with limited requests
- **Features**: Large lyrics database, translations available
- **Rate Limits**: 2,000 requests/day (free tier)
- **Note**: Lyrics snippets only in free tier, full lyrics require paid plan

**Example Request**:
```python
import requests

params = {
    'apikey': 'YOUR_API_KEY',
    'q_artist': artist,
    'q_track': song_title
}
response = requests.get('https://api.musixmatch.com/ws/1.1/matcher.lyrics.get', params=params)
```

### 3. ChartLyrics
- **Website**: http://www.chartlyrics.com/api.aspx
- **Pricing**: Free (no API key required)
- **Features**: Basic lyrics search
- **Note**: Service may be unreliable, database not frequently updated

**Example Request**:
```python
import requests

url = f'http://api.chartlyrics.com/apiv1.asmx/SearchLyricDirect?artist={artist}&song={song_title}'
response = requests.get(url)
```

### 4. AudD Music Recognition API
- **Website**: https://audd.io/
- **Pricing**: Free tier available (requires API key)
- **Features**: Music recognition + lyrics
- **Rate Limits**: 100 requests/day (free tier)

## Implementation Notes

### Security Considerations
- Store API keys in environment variables or settings service
- Never commit API keys to version control
- Implement rate limiting on your side to avoid exhausting quotas

### Caching Strategy
- Cache lyrics in database after first fetch (already implemented)
- Consider implementing expiration/refresh logic for corrections

### Legal Considerations
- Lyrics are copyrighted material
- Ensure API terms of service compliance
- Display proper attribution as required by API providers
- Genius requires attribution: "Lyrics provided by Genius"
- Musixmatch requires attribution and usage tracking

## Recommended Implementation

For MVidarr, I recommend using **Genius API**:

1. **Best Database Coverage**: Extensive library of modern and classic songs
2. **Free Tier**: Generous limits for personal use
3. **Good Documentation**: Well-maintained API with examples
4. **Additional Features**: Can also fetch song metadata, artist bio, etc.
5. **Active Service**: Regularly updated and maintained

## Adding Genius API Integration

To add Genius API to MVidarr:

1. **Get API Credentials**:
   - Visit https://genius.com/api-clients
   - Create an account and register a new API client
   - Copy your access token

2. **Add to Settings**:
   ```sql
   INSERT INTO settings (key, value) VALUES ('genius_api_token', 'YOUR_TOKEN_HERE');
   ```

3. **Update Code** (in `src/api/fastapi/videos_search.py`):
   - Replace lyrics.ovh API call with Genius API
   - Add Genius as a lyrics source
   - Handle Genius API response format

4. **Test**:
   - Try lyrics search with a popular song
   - Verify lyrics are returned and saved
   - Check attribution is displayed

## Manual Entry Workflow

Until an API is integrated:

1. User clicks "Search Lyrics" button
2. If automatic search fails, show message: "Lyrics API unavailable. Please add lyrics manually."
3. Provide text area for manual input
4. Save via `PUT /api/videos/{video_id}/lyrics` endpoint
5. Display saved lyrics

## Future Enhancements

- Multiple API fallback chain (try Genius, then Musixmatch, then manual)
- Lyrics editing interface for corrections
- Community lyrics contributions
- Lyrics synchronization (timed lyrics/LRC format)
- Lyrics translation support
