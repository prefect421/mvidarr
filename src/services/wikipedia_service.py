"""
Wikipedia API service for artist thumbnail retrieval
"""

import re

import requests

from src.utils.logger import get_logger

logger = get_logger("mvidarr.wikipedia_service")


class WikipediaService:
    def __init__(self):
        self.base_url = "https://en.wikipedia.org/api/rest_v1"
        self.search_url = "https://en.wikipedia.org/w/api.php"
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "MVidarr/1.0 (https://github.com/mvidarr) requests/2.0"}
        )

    def search_artist_thumbnail(self, artist_name):
        """
        Search for an artist's thumbnail image on Wikipedia

        Args:
            artist_name (str): Name of the artist to search for

        Returns:
            str or None: URL of the artist's thumbnail image if found
        """
        try:
            # Build list of name variations to try
            variations = [artist_name]

            # Try without "The " prefix (e.g., "The Grateful Dead" -> "Grateful Dead")
            if artist_name.lower().startswith("the "):
                variations.append(artist_name[4:])

            # Try without "A " prefix
            if artist_name.lower().startswith("a "):
                variations.append(artist_name[2:])

            # For single-word names, try adding "band" or "musician"
            if len(artist_name.split()) == 1:
                variations.extend([f"{artist_name} band", f"{artist_name} musician"])

            # Try each variation until we find a thumbnail
            for variation in variations:
                logger.debug(f"Trying Wikipedia search variation: {variation}")

                # First, search for the artist page
                page_title = self._search_artist_page(variation)
                if not page_title:
                    logger.debug(f"No Wikipedia page found for: {variation}")
                    continue

                # Get the page's main image
                thumbnail_url = self._get_page_thumbnail(page_title)
                if thumbnail_url:
                    logger.info(
                        f"Found Wikipedia thumbnail for {artist_name} (using '{variation}'): {thumbnail_url}"
                    )
                    return thumbnail_url
                else:
                    logger.debug(f"No thumbnail on Wikipedia page for: {variation}")

            logger.debug(f"No thumbnail found for any variation of: {artist_name}")
            return None

        except Exception as e:
            logger.warning(f"Error searching Wikipedia for {artist_name}: {e}")
            return None

    def _search_artist_page(self, artist_name):
        """
        Search for the artist's Wikipedia page title

        Args:
            artist_name (str): Name of the artist to search for

        Returns:
            str or None: Wikipedia page title if found
        """
        try:
            # Clean up artist name for search
            search_term = self._clean_artist_name(artist_name)

            # Search for pages
            params = {
                "action": "query",
                "format": "json",
                "list": "search",
                "srsearch": search_term,
                "srlimit": 5,
                "srwhat": "text",
            }

            response = self.session.get(self.search_url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if "query" in data and "search" in data["query"]:
                search_results = data["query"]["search"]

                # Look for the best match
                for result in search_results:
                    title = result["title"]
                    snippet = result.get("snippet", "").lower()

                    # Check if this looks like a musician/artist page
                    if self._is_likely_artist_page(title, snippet, artist_name):
                        logger.debug(f"Found Wikipedia page for {artist_name}: {title}")
                        return title

                # If no obvious artist page found, try the first result
                if search_results:
                    first_title = search_results[0]["title"]
                    logger.debug(
                        f"Using first search result for {artist_name}: {first_title}"
                    )
                    return first_title

            return None

        except Exception as e:
            logger.warning(f"Error searching Wikipedia for {artist_name}: {e}")
            return None

    def _get_page_thumbnail(self, page_title):
        """
        Get the main thumbnail image for a Wikipedia page

        Args:
            page_title (str): Wikipedia page title

        Returns:
            str or None: URL of the page's thumbnail image
        """
        try:
            # Get page info including main image
            params = {
                "action": "query",
                "format": "json",
                "titles": page_title,
                "prop": "pageimages|pageimagesthumbnails",
                "pithumbsize": 500,  # Request 500px thumbnail
                "pilimit": 1,
            }

            response = self.session.get(self.search_url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if "query" in data and "pages" in data["query"]:
                pages = data["query"]["pages"]

                for page_id, page_data in pages.items():
                    if "thumbnail" in page_data:
                        thumbnail_url = page_data["thumbnail"]["source"]
                        # Prefer larger images by modifying the URL
                        thumbnail_url = self._enhance_thumbnail_url(thumbnail_url)
                        return thumbnail_url
                    elif "pageimage" in page_data:
                        # Try to construct image URL from pageimage
                        image_title = page_data["pageimage"]
                        return self._get_image_url(image_title)

            return None

        except Exception as e:
            logger.warning(f"Error getting thumbnail for page {page_title}: {e}")
            return None

    def _get_image_url(self, image_title):
        """
        Get the full URL for a Wikipedia image

        Args:
            image_title (str): Wikipedia image title

        Returns:
            str or None: URL of the image
        """
        try:
            params = {
                "action": "query",
                "format": "json",
                "titles": f"File:{image_title}",
                "prop": "imageinfo",
                "iiprop": "url",
                "iiurlwidth": 500,
            }

            response = self.session.get(self.search_url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()

            if "query" in data and "pages" in data["query"]:
                pages = data["query"]["pages"]

                for page_id, page_data in pages.items():
                    if "imageinfo" in page_data and page_data["imageinfo"]:
                        image_info = page_data["imageinfo"][0]
                        if "thumburl" in image_info:
                            return image_info["thumburl"]
                        elif "url" in image_info:
                            return image_info["url"]

            return None

        except Exception as e:
            logger.warning(f"Error getting image URL for {image_title}: {e}")
            return None

    def _clean_artist_name(self, artist_name):
        """
        Clean up artist name for better Wikipedia search results

        Args:
            artist_name (str): Original artist name

        Returns:
            str: Cleaned artist name
        """
        # Remove common suffixes that might interfere with search
        cleaned = re.sub(r"\s*\([^)]*\)$", "", artist_name)  # Remove parenthetical info
        cleaned = re.sub(
            r"\s*(feat\.|featuring)\s.*$", "", cleaned, flags=re.IGNORECASE
        )
        cleaned = cleaned.strip()

        return cleaned

    def _is_likely_artist_page(self, title, snippet, artist_name):
        """
        Check if a Wikipedia page is likely about the artist we're looking for

        Args:
            title (str): Wikipedia page title
            snippet (str): Page snippet from search results
            artist_name (str): Original artist name we're searching for

        Returns:
            bool: True if this looks like an artist page
        """
        title_lower = title.lower()
        snippet_lower = snippet.lower()
        artist_lower = artist_name.lower()

        # Check if title contains the artist name
        if artist_lower in title_lower:
            # Look for music-related keywords in snippet
            music_keywords = [
                "band",
                "singer",
                "musician",
                "artist",
                "album",
                "song",
                "recording",
                "music",
                "vocalist",
                "guitarist",
                "drummer",
                "bassist",
                "piano",
                "rock",
                "pop",
                "hip hop",
                "rap",
                "country",
                "jazz",
                "classical",
                "electronic",
                "folk",
            ]

            # Check for disambiguation pages (usually not what we want)
            if "disambiguation" in title_lower or "may refer to" in snippet_lower:
                return False

            # Check for music-related content
            for keyword in music_keywords:
                if keyword in snippet_lower:
                    return True

        return False

    def _enhance_thumbnail_url(self, thumbnail_url):
        """
        Enhance thumbnail URL to get better quality image

        Args:
            thumbnail_url (str): Original thumbnail URL

        Returns:
            str: Enhanced thumbnail URL
        """
        # Try to increase image size by modifying URL parameters
        if "thumb" in thumbnail_url and "/thumb/" in thumbnail_url:
            # Try to get a larger version
            enhanced_url = re.sub(r"/(\d+)px-", "/800px-", thumbnail_url)
            if enhanced_url != thumbnail_url:
                return enhanced_url

        return thumbnail_url


# Global service instance
wikipedia_service = WikipediaService()
