"""
Python Client Library Generation - Issue 128 Advanced FastAPI Features
Functions for generating Python client libraries
"""

import json
import os
from typing import Any, Dict

from src.api.fastapi.client_models import ClientConfig, ClientLanguage, GeneratedClient
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.client_python_generator")


async def generate_python_client(
    spec: Dict[str, Any],
    config: ClientConfig,
    output_path: str,
    include_examples: bool = True,
) -> GeneratedClient:
    """Generate Python client library"""
    try:
        # Create Python client structure
        client_dir = os.path.join(output_path, "mvidarr_client")
        os.makedirs(client_dir, exist_ok=True)

        # Generate OpenAPI spec file
        spec_file = os.path.join(output_path, "openapi.json")
        with open(spec_file, "w") as f:
            json.dump(spec, f, indent=2)

        # Generate main client file
        client_code = generate_python_client_code(spec, config)
        with open(os.path.join(client_dir, "__init__.py"), "w") as f:
            f.write(client_code)

        # Generate models
        models_code = generate_python_models(spec)
        with open(os.path.join(client_dir, "models.py"), "w") as f:
            f.write(models_code)

        # Generate API classes
        api_code = generate_python_api_classes(spec)
        with open(os.path.join(client_dir, "api.py"), "w") as f:
            f.write(api_code)

        # Generate setup.py
        setup_code = generate_python_setup(config)
        with open(os.path.join(output_path, "setup.py"), "w") as f:
            f.write(setup_code)

        # Generate examples
        examples_dir = os.path.join(output_path, "examples")
        if include_examples:
            os.makedirs(examples_dir, exist_ok=True)
            examples_code = generate_python_examples(config)
            with open(os.path.join(examples_dir, "basic_usage.py"), "w") as f:
                f.write(examples_code)

        # Generate requirements.txt
        with open(os.path.join(output_path, "requirements.txt"), "w") as f:
            f.write("requests>=2.25.0\ntyping-extensions>=3.7.4\n")

        # Generate README
        readme_content = generate_python_readme(config)
        with open(os.path.join(output_path, "README.md"), "w") as f:
            f.write(readme_content)

        files_generated = [
            "mvidarr_client/__init__.py",
            "mvidarr_client/models.py",
            "mvidarr_client/api.py",
            "setup.py",
            "requirements.txt",
            "README.md",
        ]

        if include_examples:
            files_generated.append("examples/basic_usage.py")

        return GeneratedClient(
            language=ClientLanguage.PYTHON,
            package_name=config.package_name,
            version=config.version,
            output_path=output_path,
            files_generated=files_generated,
            examples_included=include_examples,
            documentation_path=os.path.join(output_path, "README.md"),
            installation_instructions="pip install -e .",
        )

    except Exception as e:
        logger.error(f"Failed to generate Python client: {e}")
        raise


def generate_python_client_code(spec: Dict[str, Any], config: ClientConfig) -> str:
    """Generate Python client code"""
    return '''"""
MVidarr Python Client Library
Generated automatically from OpenAPI specification
"""

import requests
import json
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

class MVidarrClient:
    """Python client for MVidarr API"""

    def __init__(self, base_url: str = "http://localhost:5000", api_key: Optional[str] = None):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()

        if api_key:
            self.session.headers.update({"X-API-Key": api_key})

        # Set common headers
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "MVidarr-Python-Client/1.0.0"
        })

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to API"""
        url = urljoin(f"{self.base_url}/", endpoint.lstrip('/'))

        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise Exception(f"API request failed: {e}")

    # Videos API
    def get_videos(self, page: int = 1, per_page: int = 50) -> Dict[str, Any]:
        """Get list of videos"""
        return self._make_request("GET", "/api/videos", params={"page": page, "per_page": per_page})

    def get_video(self, video_id: int) -> Dict[str, Any]:
        """Get single video by ID"""
        return self._make_request("GET", f"/api/videos/{video_id}")

    def create_video(self, video_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new video"""
        return self._make_request("POST", "/api/videos", json=video_data)

    def update_video(self, video_id: int, video_data: Dict[str, Any]) -> Dict[str, Any]:
        """Update existing video"""
        return self._make_request("PUT", f"/api/videos/{video_id}", json=video_data)

    def delete_video(self, video_id: int) -> Dict[str, Any]:
        """Delete video"""
        return self._make_request("DELETE", f"/api/videos/{video_id}")

    # Artists API
    def get_artists(self, page: int = 1, per_page: int = 50) -> Dict[str, Any]:
        """Get list of artists"""
        return self._make_request("GET", "/api/artists", params={"page": page, "per_page": per_page})

    def get_artist(self, artist_id: int) -> Dict[str, Any]:
        """Get single artist by ID"""
        return self._make_request("GET", f"/api/artists/{artist_id}")

    # Playlists API
    def get_playlists(self) -> Dict[str, Any]:
        """Get user playlists"""
        return self._make_request("GET", "/api/playlists")

    def create_playlist(self, playlist_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new playlist"""
        return self._make_request("POST", "/api/playlists", json=playlist_data)
'''


def generate_python_models(spec: Dict[str, Any]) -> str:
    """Generate Python model classes"""
    return '''"""
MVidarr API Models
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime

@dataclass
class Video:
    id: int
    title: str
    artist_id: Optional[int] = None
    artist_name: Optional[str] = None
    duration: Optional[int] = None
    file_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class Artist:
    id: int
    name: str
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

@dataclass
class Playlist:
    id: int
    name: str
    description: Optional[str] = None
    user_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
'''


def generate_python_api_classes(spec: Dict[str, Any]) -> str:
    """Generate Python API classes"""
    return '''"""
MVidarr API Classes
"""

from typing import Dict, Any, List, Optional
from .models import Video, Artist, Playlist

class VideosAPI:
    """Videos API endpoints"""

    def __init__(self, client):
        self.client = client

    def list_videos(self, **params) -> List[Video]:
        """List videos with optional filtering"""
        response = self.client._make_request("GET", "/api/videos", params=params)
        return [Video(**video_data) for video_data in response.get("videos", [])]

    def get_video(self, video_id: int) -> Video:
        """Get video by ID"""
        response = self.client._make_request("GET", f"/api/videos/{video_id}")
        return Video(**response)

class ArtistsAPI:
    """Artists API endpoints"""

    def __init__(self, client):
        self.client = client

    def list_artists(self, **params) -> List[Artist]:
        """List artists with optional filtering"""
        response = self.client._make_request("GET", "/api/artists", params=params)
        return [Artist(**artist_data) for artist_data in response.get("artists", [])]
'''


def generate_python_setup(config: ClientConfig) -> str:
    """Generate Python setup.py"""
    return f"""from setuptools import setup, find_packages

setup(
    name="{config.package_name}",
    version="{config.version}",
    description="{config.description}",
    author="{config.author}",
    license="{config.license}",
    packages=find_packages(),
    install_requires=[
        "requests>=2.25.0",
        "typing-extensions>=3.7.4"
    ],
    python_requires=">=3.7",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
    ]
)
"""


def generate_python_examples(config: ClientConfig) -> str:
    """Generate Python usage examples"""
    return '''#!/usr/bin/env python3
"""
MVidarr Python Client - Basic Usage Examples
"""

from mvidarr_client import MVidarrClient

# Initialize client
client = MVidarrClient(base_url="http://localhost:5000")

# Get videos
print("Fetching videos...")
videos = client.get_videos(page=1, per_page=10)
print(f"Found {len(videos.get('videos', []))} videos")

# Get specific video
if videos.get('videos'):
    video_id = videos['videos'][0]['id']
    video = client.get_video(video_id)
    print(f"Video: {video.get('title')}")

# Get artists
print("\\nFetching artists...")
artists = client.get_artists()
print(f"Found {len(artists.get('artists', []))} artists")

# Get playlists
print("\\nFetching playlists...")
playlists = client.get_playlists()
print(f"Found {len(playlists.get('playlists', []))} playlists")
'''


def generate_python_readme(config: ClientConfig) -> str:
    """Generate Python README"""
    return f"""# {config.package_name}

{config.description}

## Installation

```bash
pip install -e .
```

## Quick Start

```python
from mvidarr_client import MVidarrClient

# Initialize client
client = MVidarrClient(base_url="http://localhost:5000")

# Get videos
videos = client.get_videos()
print(f"Found {{len(videos['videos'])}} videos")

# Get artists
artists = client.get_artists()
print(f"Found {{len(artists['artists'])}} artists")
```

## API Documentation

For complete API documentation, see the [MVidarr API Documentation](http://localhost:5000/docs).

## License

{config.license}
"""
