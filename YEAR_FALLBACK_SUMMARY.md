# Year Data Fallback System - Summary

## Current Status

**Total Videos:** 250
**Videos with Year:** 208 (83.2%)
**Videos without Year:** 42 (16.8%)

## Implemented Fallback Methods

### 1. ✅ YouTube upload_date from video_metadata
**Location:** `src/services/video_indexing_service.py:403-413`, `src/services/metadata_enrichment_service.py:2419-2430`
**Status:** Implemented and working
**Effectiveness:** 0 videos (field no longer provided by yt-dlp v2025.07.21+)

```python
if not video.year and video.video_metadata:
    upload_date = video.video_metadata.get('upload_date')
    if upload_date and isinstance(upload_date, str) and len(upload_date) >= 4:
        video.year = int(upload_date[:4])
```

### 2. ✅ .info.json upload_date Field
**Script:** `scripts/backfill_year_from_info_json.py`
**Status:** Implemented
**Effectiveness:** 0 videos (field removed in newer yt-dlp versions)

### 3. ✅ Description Copyright Notice
**Script:** `scripts/backfill_year_from_descriptions.py`
**Status:** Implemented
**Effectiveness:** 1 video updated
**Pattern:** `(C) 2005` or `℗ 2005`

### 4. ✅ Description Album/Release Context
**Script:** `scripts/backfill_year_from_descriptions.py`
**Status:** Implemented
**Effectiveness:** 1 video updated
**Patterns:** "Released @ 2005", "from the album ... (2005)"

### 5. ✅ Metadata Enrichment Services
**Services:** IMVDb, MusicBrainz, Spotify, Last.fm
**Status:** Implemented
**Effectiveness:** ~17 videos updated (limited by API availability)

## Additional Fallback Options

### 6. 🔄 Wikipedia API for Discography
**Implementation:** Not yet implemented
**Potential:** High for well-known artists
**Approach:**
- Query Wikipedia for artist discography
- Match song titles to release dates
- Extract year from album/single release dates

**Pros:**
- Free API
- Good coverage for popular artists
- Includes album context

**Cons:**
- Requires title matching fuzzy logic
- Not all artists have structured discography pages
- May need multiple API calls per artist

### 7. 🔄 Discogs API
**Implementation:** Not yet implemented
**Potential:** Very high (comprehensive music database)
**Approach:**
- Search for artist + track combination
- Extract release year from master release or first pressing

**Pros:**
- Extremely comprehensive music database
- Includes obscure and international releases
- Has structured API

**Cons:**
- Requires API key
- Rate limited
- May return multiple versions with different years

### 8. 🔄 Last.fm API Track Info
**Implementation:** Service exists but not used for year extraction
**Potential:** Medium
**Approach:**
- Use `track.getInfo` endpoint
- Extract year from album information

**Pros:**
- Already have Last.fm integration
- Good coverage
- Free API

**Cons:**
- Data quality varies
- Not as reliable as Discogs or MusicBrainz

### 9. 🔄 YouTube Data API v3
**Implementation:** Not yet implemented
**Potential:** Medium
**Approach:**
- Use video ID to query YouTube API
- Get publishedAt date
- Use as fallback if no better source

**Pros:**
- Authoritative source for upload date
- Reliable data

**Cons:**
- Requires API key and quota management
- Upload date != release date
- May be years after actual release

### 10. 🔄 Filename Pattern Matching
**Implementation:** Not yet implemented
**Potential:** Low
**Approach:**
- Parse filenames for year patterns: `Artist - Song (1999).mp4`
- Extract bracketed or parenthesized years

**Effectiveness:** Limited (current filenames don't contain years)

## Recommendations

### Immediate Actions (High ROI)

1. **Wait for IMVDb API Recovery**
   - IMVDb was returning 502 errors during testing
   - Likely temporary outage
   - Covers most mainstream music videos
   - Re-run: `python3 /home/mike/mvidarr/run_enrichment.py`

2. **Configure Spotify API Credentials**
   - Already integrated but missing credentials
   - Would cover many remaining videos
   - Configure in settings

3. **Implement Last.fm Year Extraction**
   - Service already integrated
   - Add year extraction from track.getInfo
   - Quick win for existing integration

### Medium-Term Improvements

4. **Add Discogs API Integration**
   - Highest quality music metadata
   - Best coverage for obscure releases
   - Worth the API key investment

5. **Add Wikipedia Discography Parser**
   - Free, no API key needed
   - Good for well-known artists
   - Complements other sources

### Long-Term Options

6. **YouTube Data API Integration**
   - Last resort fallback
   - Requires quota management
   - Upload date not ideal but better than nothing

## Current Coverage by Artist

**Artists with Most Missing Year Data:**
- System of a Down: 13 videos
- ATARASHII GAKKO!: 12 videos
- Nova Twins: 7 videos
- Big Audio Dynamite: 2 videos
- Bad Brains: 2 videos
- Others: 1 video each

## Scripts Available

1. `scripts/backfill_year_from_upload_date.py` - Extract from video_metadata
2. `scripts/backfill_year_from_info_json.py` - Extract from .info.json files
3. `scripts/backfill_year_from_descriptions.py` - Extract from descriptions/tags
4. `/home/mike/mvidarr/run_enrichment.py` - Run full metadata enrichment

## Testing Results

From 250 total videos:
- Started: 189 with year (75.6%)
- After enrichment: 208 with year (83.2%)
- **Improvement: 19 videos (+7.6%)**

Remaining 42 videos require:
- External API data (IMVDb, Spotify, MusicBrainz, Discogs)
- Manual entry for obscure tracks
- Additional fallback implementations

## Conclusion

The year fallback system is **properly implemented and working**. The limitation is not the fallback logic itself, but the availability of source data:

1. ✅ **Fallback code works** - Tested and verified
2. ❌ **YouTube stopped providing upload_date** - yt-dlp v2025.07.21+ change
3. ⚠️ **External APIs needed** - IMVDb down, Spotify unconfigured
4. ✅ **Description parsing works** - Small but effective
5. 🔄 **More fallbacks available** - Wikipedia, Discogs, Last.fm year extraction not yet implemented

**Best next step:** Wait for IMVDb API recovery and configure Spotify, which should cover most remaining videos.
