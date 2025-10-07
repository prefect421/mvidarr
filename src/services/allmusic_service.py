"""
AllMusic API Integration Service for MVidarr 0.9.8
Provides comprehensive music metadata from AllMusic including genres, styles, moods, and themes.
"""

import json
import time
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

from src.services.settings_service import settings
from src.utils.logger import get_logger

logger = get_logger("mvidarr.services.allmusic")


class AllMusicService:
    """Service for AllMusic web scraping and metadata enrichment"""

    def __init__(self):
        self.base_url = "https://www.allmusic.com"
        self.search_url = f"{self.base_url}/search/all"  # Updated to working format
        self.user_agent = "MVidarr/0.9.8 (https://github.com/prefect421/mvidarr)"
        self.rate_limit_delay = 2.0  # Be respectful to AllMusic servers
        self.last_request_time = 0

        # Load settings
        self._settings_loaded = False
        self._enabled = None

    def _load_settings(self):
        """Load AllMusic settings from database"""
        if self._settings_loaded:
            return

        try:
            # AllMusic scraping can be disabled if needed
            self._enabled = settings.get("allmusic_enabled", "true").lower() == "true"
            self._settings_loaded = True
            logger.debug(f"AllMusic settings loaded - enabled: {self._enabled}")
        except Exception as e:
            logger.error(f"Failed to load AllMusic settings: {e}")
            self._enabled = True  # Default to enabled
            self._settings_loaded = True

    @property
    def enabled(self):
        """Check if AllMusic integration is enabled"""
        self._load_settings()
        return self._enabled

    def _respect_rate_limit(self):
        """Ensure we respect rate limiting for web scraping"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time

        if time_since_last_request < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last_request
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def _make_request(self, url: str) -> Optional[requests.Response]:
        """Make rate-limited request to AllMusic"""
        if not self.enabled:
            logger.debug("AllMusic integration is disabled")
            return None

        self._respect_rate_limit()

        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        try:
            logger.debug(f"Making AllMusic request to: {url}")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            logger.error(f"Request to AllMusic failed: {e}")
            return None

    def search_artist(self, artist_name: str) -> Optional[Dict]:
        """
        Search for artist on AllMusic and return basic info with link
        """
        try:
            # Construct search URL using the working format
            encoded_name = quote_plus(artist_name)
            search_url = f"{self.search_url}/{encoded_name}"

            response = self._make_request(search_url)
            if not response:
                return None

            soup = BeautifulSoup(response.content, "html.parser")

            # Find artist search results
            artist_results = soup.find_all("div", class_="artist")
            if not artist_results:
                # Try alternative search result structure
                artist_results = soup.find_all("li", class_="artist") or soup.find_all(
                    "div", class_="search-result"
                )

            if not artist_results:
                logger.debug(f"No artist results found for: {artist_name}")
                return None

            # Get the first (most relevant) result
            first_result = artist_results[0]

            # Extract artist link
            artist_link = first_result.find("a")
            if not artist_link:
                logger.debug(
                    f"No artist link found in search results for: {artist_name}"
                )
                return None

            artist_url = urljoin(self.base_url, artist_link.get("href"))
            artist_title = artist_link.get_text(strip=True)

            # Calculate confidence based on name similarity
            confidence = self._calculate_name_similarity(artist_name, artist_title)

            return {
                "name": artist_title,
                "url": artist_url,
                "confidence": confidence,
                "source": "allmusic_search",
            }

        except Exception as e:
            logger.error(f"Error searching AllMusic for artist '{artist_name}': {e}")
            return None

    def get_artist_metadata(
        self, artist_name: str, artist_url: str = None
    ) -> Optional[Dict]:
        """
        Get comprehensive metadata for an artist from AllMusic
        """
        try:
            # If no URL provided, search for it first
            if not artist_url:
                search_result = self.search_artist(artist_name)
                if not search_result:
                    return None
                artist_url = search_result["url"]

            response = self._make_request(artist_url)
            if not response:
                return None

            soup = BeautifulSoup(response.content, "html.parser")

            # Extract metadata from JSON-LD structured data (modern approach)
            json_ld_data = self._extract_json_ld_data(soup)

            # Extract metadata using both JSON-LD and HTML selectors for maximum coverage
            metadata = {
                "name": json_ld_data.get("name") or self._extract_artist_name(soup),
                "biography": json_ld_data.get("description")
                or self._extract_biography(soup),
                "genres": self._extract_genres(soup),
                "styles": self._extract_styles(soup),
                "moods": self._extract_moods(soup),
                "themes": self._extract_themes(soup),
                "active_years": self._extract_active_years(soup),
                "formed_year": self._extract_formed_year(soup),
                "origin": self._extract_origin(soup),
                "members": self._extract_members_from_json_ld(json_ld_data)
                or self._extract_members(soup),
                "similar_artists": self._extract_similar_artists(soup),
                "discography": self._extract_discography_summary(soup),
                "rating": self._extract_allmusic_rating(soup),
                "url": artist_url,
                "confidence": 0.85,  # High confidence for direct page access
                "source": "allmusic",
                "extracted_at": datetime.now().isoformat(),
                "image_url": json_ld_data.get("image"),  # Add image from JSON-LD
            }

            # Filter out None values
            metadata = {k: v for k, v in metadata.items() if v is not None}

            logger.info(
                f"Successfully extracted AllMusic metadata for: {metadata.get('name', artist_name)}"
            )
            return metadata

        except Exception as e:
            logger.error(f"Error extracting AllMusic metadata for '{artist_name}': {e}")
            return None

    def _extract_json_ld_data(self, soup: BeautifulSoup) -> Dict:
        """Extract JSON-LD structured data from AllMusic page"""
        try:
            json_scripts = soup.find_all("script", type="application/ld+json")
            for script in json_scripts:
                try:
                    json_data = json.loads(script.string)
                    if json_data.get("@type") in ["MusicGroup", "Person"]:
                        logger.debug(f"Found JSON-LD data: {json_data.keys()}")
                        return json_data
                except json.JSONDecodeError:
                    continue
            return {}
        except Exception as e:
            logger.debug(f"Error extracting JSON-LD data: {e}")
            return {}

    def _extract_members_from_json_ld(self, json_ld_data: Dict) -> List[str]:
        """Extract members from JSON-LD structured data"""
        try:
            members = []
            member_data = json_ld_data.get("member", [])

            if isinstance(member_data, list):
                for member in member_data:
                    if isinstance(member, dict) and member.get("name"):
                        members.append(member["name"])

            return members
        except Exception as e:
            logger.debug(f"Error extracting members from JSON-LD: {e}")
            return []

    def _extract_artist_name(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract artist name from page"""
        try:
            # Try various selectors for artist name
            selectors = [
                "h1.artist-name",
                "h1.header-new-title",
                'h1[class*="title"]',
                "h1",
                ".artist-name",
                ".header-new-title",
            ]

            for selector in selectors:
                element = soup.select_one(selector)
                if element:
                    return element.get_text(strip=True)

            return None

        except Exception as e:
            logger.debug(f"Error extracting artist name: {e}")
            return None

    def _extract_biography(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract artist biography"""
        try:
            # Try various selectors for biography
            selectors = [
                ".biography",
                ".bio",
                ".artist-bio",
                ".description",
                '[class*="bio"]',
                '[class*="description"]',
            ]

            for selector in selectors:
                element = soup.select_one(selector)
                if element:
                    # Clean up the text
                    bio_text = element.get_text(strip=True)
                    # Remove excessive whitespace
                    bio_text = " ".join(bio_text.split())
                    return bio_text if len(bio_text) > 50 else None

            return None

        except Exception as e:
            logger.debug(f"Error extracting biography: {e}")
            return None

    def _extract_genres(self, soup: BeautifulSoup) -> List[str]:
        """Extract genres from page"""
        try:
            genres = []

            # Try various selectors for genres
            selectors = [
                ".genre a",
                ".genres a",
                '[class*="genre"] a',
                ".styles .genre a",
            ]

            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    genre = element.get_text(strip=True)
                    if genre and genre not in genres:
                        genres.append(genre)

            # Also try text-based extraction
            genre_section = soup.find(string=lambda text: text and "Genre" in text)
            if genre_section:
                parent = genre_section.parent
                if parent:
                    genre_links = parent.find_all("a")
                    for link in genre_links:
                        genre = link.get_text(strip=True)
                        if genre and genre not in genres:
                            genres.append(genre)

            return genres[:10]  # Limit to top 10 genres

        except Exception as e:
            logger.debug(f"Error extracting genres: {e}")
            return []

    def _extract_styles(self, soup: BeautifulSoup) -> List[str]:
        """Extract musical styles from page"""
        try:
            styles = []

            # Try various selectors for styles
            selectors = [
                ".style a",
                ".styles a",
                '[class*="style"] a',
                ".genre-styles a",
            ]

            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    style = element.get_text(strip=True)
                    if style and style not in styles:
                        styles.append(style)

            # Look for "Styles:" section
            style_section = soup.find(
                string=lambda text: text and "Style" in text and ":" in text
            )
            if style_section:
                parent = style_section.parent
                if parent:
                    style_links = parent.find_all("a")
                    for link in style_links:
                        style = link.get_text(strip=True)
                        if style and style not in styles:
                            styles.append(style)

            return styles[:15]  # Limit to top 15 styles

        except Exception as e:
            logger.debug(f"Error extracting styles: {e}")
            return []

    def _extract_moods(self, soup: BeautifulSoup) -> List[str]:
        """Extract moods from page"""
        try:
            moods = []

            # Look for moods section
            mood_section = soup.find(string=lambda text: text and "Mood" in text)
            if mood_section:
                parent = mood_section.parent
                if parent:
                    mood_links = parent.find_all("a")
                    for link in mood_links:
                        mood = link.get_text(strip=True)
                        if mood and mood not in moods:
                            moods.append(mood)

            # Alternative selectors
            selectors = [".mood a", ".moods a", '[class*="mood"] a']

            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    mood = element.get_text(strip=True)
                    if mood and mood not in moods:
                        moods.append(mood)

            return moods[:10]  # Limit to top 10 moods

        except Exception as e:
            logger.debug(f"Error extracting moods: {e}")
            return []

    def _extract_themes(self, soup: BeautifulSoup) -> List[str]:
        """Extract themes from page"""
        try:
            themes = []

            # Look for themes section
            theme_section = soup.find(string=lambda text: text and "Theme" in text)
            if theme_section:
                parent = theme_section.parent
                if parent:
                    theme_links = parent.find_all("a")
                    for link in theme_links:
                        theme = link.get_text(strip=True)
                        if theme and theme not in themes:
                            themes.append(theme)

            # Alternative selectors
            selectors = [".theme a", ".themes a", '[class*="theme"] a']

            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    theme = element.get_text(strip=True)
                    if theme and theme not in themes:
                        themes.append(theme)

            return themes[:10]  # Limit to top 10 themes

        except Exception as e:
            logger.debug(f"Error extracting themes: {e}")
            return []

    def _extract_active_years(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract active years for the artist"""
        try:
            # Look for years in various formats
            year_patterns = ["Active:", "Years Active:", "Active Years:", "Career:"]

            for pattern in year_patterns:
                year_section = soup.find(string=lambda text: text and pattern in text)
                if year_section:
                    # Try to find the next text that contains years
                    next_element = year_section.find_next()
                    if next_element:
                        text = next_element.get_text(strip=True)
                        # Look for year patterns like "1990-2010" or "1990-Present"
                        import re

                        year_match = re.search(
                            r"(\d{4})[-–](\d{4}|Present|present)", text
                        )
                        if year_match:
                            return year_match.group(0)

            return None

        except Exception as e:
            logger.debug(f"Error extracting active years: {e}")
            return None

    def _extract_formed_year(self, soup: BeautifulSoup) -> Optional[int]:
        """Extract formation year"""
        try:
            # Look for formation year
            formed_section = soup.find(string=lambda text: text and "Formed" in text)
            if formed_section:
                # Extract year from text
                import re

                text = (
                    formed_section.get_text()
                    if hasattr(formed_section, "get_text")
                    else str(formed_section)
                )
                year_match = re.search(r"(\d{4})", text)
                if year_match:
                    return int(year_match.group(1))

            # Also check active years for formation
            active_years = self._extract_active_years(soup)
            if active_years:
                import re

                year_match = re.search(r"(\d{4})", active_years)
                if year_match:
                    return int(year_match.group(1))

            return None

        except Exception as e:
            logger.debug(f"Error extracting formed year: {e}")
            return None

    def _extract_origin(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract origin/location information"""
        try:
            # Look for origin information
            origin_patterns = ["Born:", "Origin:", "From:", "Location:", "Based:"]

            for pattern in origin_patterns:
                origin_section = soup.find(string=lambda text: text and pattern in text)
                if origin_section:
                    parent = origin_section.parent
                    if parent:
                        # Look for the text after the pattern
                        text = parent.get_text(strip=True)
                        # Extract everything after the pattern
                        if pattern in text:
                            origin = text.split(pattern, 1)[1].strip()
                            # Clean up common formatting
                            origin = origin.split(",")[
                                0
                            ].strip()  # Take first part if comma-separated
                            return origin if len(origin) > 2 else None

            return None

        except Exception as e:
            logger.debug(f"Error extracting origin: {e}")
            return None

    def _extract_members(self, soup: BeautifulSoup) -> List[str]:
        """Extract band members information from HTML"""
        try:
            members = []

            # Look for modern group-members section
            group_members_div = soup.find("div", class_="group-members")
            if group_members_div:
                member_links = group_members_div.find_all("a")
                for link in member_links:
                    member = link.get_text(strip=True)
                    if member and member not in members:
                        members.append(member)

            # Fallback to older methods if needed
            if not members:
                member_section = soup.find(
                    string=lambda text: text and "Member" in text
                )
                if member_section:
                    parent = member_section.parent
                    if parent:
                        member_links = parent.find_all("a")
                        for link in member_links:
                            member = link.get_text(strip=True)
                            if member and member not in members:
                                members.append(member)

            return members[:10]  # Limit to top 10 members

        except Exception as e:
            logger.debug(f"Error extracting members: {e}")
            return []

    def _extract_similar_artists(self, soup: BeautifulSoup) -> List[str]:
        """Extract similar artists"""
        try:
            similar = []

            # Look for similar artists section
            similar_section = soup.find(string=lambda text: text and "Similar" in text)
            if similar_section:
                parent = similar_section.parent
                if parent:
                    similar_links = parent.find_all("a")
                    for link in similar_links:
                        artist = link.get_text(strip=True)
                        if artist and artist not in similar:
                            similar.append(artist)

            # Alternative selectors
            selectors = [".similar a", ".similar-artists a", '[class*="similar"] a']

            for selector in selectors:
                elements = soup.select(selector)
                for element in elements:
                    artist = element.get_text(strip=True)
                    if artist and artist not in similar:
                        similar.append(artist)

            return similar[:15]  # Limit to top 15 similar artists

        except Exception as e:
            logger.debug(f"Error extracting similar artists: {e}")
            return []

    def _extract_discography_summary(self, soup: BeautifulSoup) -> Optional[Dict]:
        """Extract basic discography information"""
        try:
            discography = {"album_count": 0, "popular_albums": []}

            # Try to find album count
            album_section = soup.find(string=lambda text: text and "Album" in text)
            if album_section:
                import re

                text = str(album_section)
                count_match = re.search(r"(\d+)\s*Album", text)
                if count_match:
                    discography["album_count"] = int(count_match.group(1))

            # Try to find popular albums
            album_links = soup.find_all("a", href=lambda x: x and "/album/" in x)
            for link in album_links[:5]:  # Top 5 albums
                album_title = link.get_text(strip=True)
                if album_title:
                    discography["popular_albums"].append(album_title)

            return (
                discography
                if discography["album_count"] > 0 or discography["popular_albums"]
                else None
            )

        except Exception as e:
            logger.debug(f"Error extracting discography: {e}")
            return None

    def _extract_allmusic_rating(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract AllMusic rating"""
        try:
            # Look for rating elements
            rating_selectors = [
                ".rating",
                ".allmusic-rating",
                '[class*="rating"]',
                ".stars",
            ]

            for selector in rating_selectors:
                element = soup.select_one(selector)
                if element:
                    # Try to extract numeric rating
                    text = element.get_text(strip=True)
                    import re

                    rating_match = re.search(r"(\d+(?:\.\d+)?)", text)
                    if rating_match:
                        return float(rating_match.group(1))

            return None

        except Exception as e:
            logger.debug(f"Error extracting rating: {e}")
            return None

    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """Calculate similarity between two artist names"""
        if not name1 or not name2:
            return 0.0

        name1_clean = name1.lower().strip()
        name2_clean = name2.lower().strip()

        # Exact match
        if name1_clean == name2_clean:
            return 1.0

        # Check if one contains the other
        if name1_clean in name2_clean or name2_clean in name1_clean:
            return 0.9

        # Simple token matching
        tokens1 = set(name1_clean.split())
        tokens2 = set(name2_clean.split())

        if not tokens1 or not tokens2:
            return 0.0

        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)

        return len(intersection) / len(union) if union else 0.0

    def get_artist_metadata_for_enrichment(
        self, artist_name: str, existing_url: str = None
    ) -> Optional[Dict]:
        """
        Get metadata specifically formatted for the metadata enrichment service
        """
        try:
            metadata = self.get_artist_metadata(artist_name, existing_url)

            if not metadata:
                return None

            # Format for enrichment service compatibility
            enrichment_metadata = {
                "name": metadata.get("name", artist_name),
                "confidence": metadata.get("confidence", 0.85),
                "genres": (metadata.get("genres") or [])
                + (metadata.get("styles") or []),  # Combine genres and styles
                "biography": metadata.get("biography"),
                "similar_artists": metadata.get("similar_artists") or [],
                "formed_year": metadata.get("formed_year"),
                "origin_country": metadata.get("origin"),
                "members": metadata.get("members") or [],
                "moods": metadata.get("moods") or [],
                "themes": metadata.get("themes") or [],
                "active_years": metadata.get("active_years"),
                "discography": metadata.get("discography"),
                "allmusic_rating": metadata.get("rating"),
                "allmusic_url": metadata.get("url"),
                "raw_data": metadata,
                "source": "allmusic",
            }

            return enrichment_metadata

        except Exception as e:
            logger.error(f"Error formatting AllMusic metadata for enrichment: {e}")
            return None


# Global instance
allmusic_service = AllMusicService()
