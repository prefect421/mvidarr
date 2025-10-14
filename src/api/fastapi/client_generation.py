"""
Client Library Generation - Issue 128 Advanced FastAPI Features
Auto-generated client libraries for multiple programming languages
"""

import json
import os
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.client_generation")


class ClientLanguage(Enum):
    """Supported client library languages"""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"
    PHP = "php"
    RUBY = "ruby"
    SWIFT = "swift"


@dataclass
class ClientConfig:
    """Client library configuration"""

    language: ClientLanguage
    package_name: str
    version: str
    description: str
    author: str
    license: str
    output_dir: str
    additional_properties: Dict[str, Any]


@dataclass
class GeneratedClient:
    """Generated client library information"""

    language: ClientLanguage
    package_name: str
    version: str
    output_path: str
    files_generated: List[str]
    examples_included: bool
    documentation_path: Optional[str]
    installation_instructions: str


class ClientLibraryGenerator:
    """Generates client libraries from OpenAPI specification"""

    def __init__(self, app: FastAPI, config: Optional[Dict] = None):
        self.app = app
        self.config = config or {}

        # Generator configuration
        self.output_base_dir = self.config.get("output_dir", "/tmp/mvidarr_clients")
        self.openapi_generator_jar = self.config.get("generator_jar_path")
        self.include_examples = self.config.get("include_examples", True)
        self.generate_docs = self.config.get("generate_docs", True)

        # Default client configurations
        self.default_configs = {
            ClientLanguage.PYTHON: ClientConfig(
                language=ClientLanguage.PYTHON,
                package_name="mvidarr-client",
                version="1.0.0",
                description="Python client library for MVidarr API",
                author="MVidarr Team",
                license="MIT",
                output_dir="python-client",
                additional_properties={
                    "projectName": "mvidarr-client",
                    "packageName": "mvidarr_client",
                    "packageVersion": "1.0.0",
                    "clientPackage": "mvidarr_client",
                    "generateSourceCodeOnly": "false",
                },
            ),
            ClientLanguage.JAVASCRIPT: ClientConfig(
                language=ClientLanguage.JAVASCRIPT,
                package_name="mvidarr-js-client",
                version="1.0.0",
                description="JavaScript client library for MVidarr API",
                author="MVidarr Team",
                license="MIT",
                output_dir="javascript-client",
                additional_properties={
                    "projectName": "mvidarr-js-client",
                    "clientPackage": "mvidarr-client",
                    "npmName": "mvidarr-js-client",
                    "npmVersion": "1.0.0",
                },
            ),
            ClientLanguage.TYPESCRIPT: ClientConfig(
                language=ClientLanguage.TYPESCRIPT,
                package_name="mvidarr-ts-client",
                version="1.0.0",
                description="TypeScript client library for MVidarr API",
                author="MVidarr Team",
                license="MIT",
                output_dir="typescript-client",
                additional_properties={
                    "projectName": "mvidarr-ts-client",
                    "npmName": "mvidarr-ts-client",
                    "npmVersion": "1.0.0",
                    "supportsES6": "true",
                },
            ),
            ClientLanguage.JAVA: ClientConfig(
                language=ClientLanguage.JAVA,
                package_name="mvidarr-java-client",
                version="1.0.0",
                description="Java client library for MVidarr API",
                author="MVidarr Team",
                license="MIT",
                output_dir="java-client",
                additional_properties={
                    "groupId": "com.mvidarr",
                    "artifactId": "mvidarr-client",
                    "artifactVersion": "1.0.0",
                    "clientPackage": "com.mvidarr.client",
                },
            ),
            ClientLanguage.GO: ClientConfig(
                language=ClientLanguage.GO,
                package_name="mvidarr-go-client",
                version="1.0.0",
                description="Go client library for MVidarr API",
                author="MVidarr Team",
                license="MIT",
                output_dir="go-client",
                additional_properties={
                    "packageName": "mvidarr",
                    "clientPackage": "mvidarr",
                },
            ),
        }

    def get_openapi_spec(self) -> Dict[str, Any]:
        """Get OpenAPI specification from FastAPI app"""
        return get_openapi(
            title="MVidarr API",
            version="2.0.0",
            description="Consumer-focused music video collection management API",
            routes=self.app.routes,
            servers=[
                {"url": "http://localhost:5000", "description": "Local development"},
                {"url": "https://api.mvidarr.local", "description": "Local network"},
            ],
        )

    async def generate_client(
        self,
        language: ClientLanguage,
        custom_config: Optional[ClientConfig] = None,
        output_dir: Optional[str] = None,
    ) -> GeneratedClient:
        """Generate client library for specified language"""
        try:
            # Use custom config or default
            config = custom_config or self.default_configs.get(language)
            if not config:
                raise ValueError(f"No configuration available for {language.value}")

            # Set output directory
            if output_dir:
                config.output_dir = output_dir

            full_output_path = os.path.join(self.output_base_dir, config.output_dir)
            os.makedirs(full_output_path, exist_ok=True)

            # Generate based on language
            if language == ClientLanguage.PYTHON:
                return await self._generate_python_client(config, full_output_path)
            elif language == ClientLanguage.JAVASCRIPT:
                return await self._generate_javascript_client(config, full_output_path)
            elif language == ClientLanguage.TYPESCRIPT:
                return await self._generate_typescript_client(config, full_output_path)
            elif language in [ClientLanguage.JAVA, ClientLanguage.GO]:
                return await self._generate_openapi_client(config, full_output_path)
            else:
                return await self._generate_custom_client(config, full_output_path)

        except Exception as e:
            logger.error(f"Failed to generate {language.value} client: {e}")
            raise

    async def generate_all_clients(self) -> Dict[ClientLanguage, GeneratedClient]:
        """Generate client libraries for all supported languages"""
        results = {}

        for language in [
            ClientLanguage.PYTHON,
            ClientLanguage.JAVASCRIPT,
            ClientLanguage.TYPESCRIPT,
        ]:
            try:
                client = await self.generate_client(language)
                results[language] = client
                logger.info(f"Generated {language.value} client successfully")
            except Exception as e:
                logger.error(f"Failed to generate {language.value} client: {e}")

        return results

    async def _generate_python_client(
        self, config: ClientConfig, output_path: str
    ) -> GeneratedClient:
        """Generate Python client library"""
        try:
            # Create Python client structure
            client_dir = os.path.join(output_path, "mvidarr_client")
            os.makedirs(client_dir, exist_ok=True)

            # Generate OpenAPI spec file
            spec = self.get_openapi_spec()
            spec_file = os.path.join(output_path, "openapi.json")
            with open(spec_file, "w") as f:
                json.dump(spec, f, indent=2)

            # Generate main client file
            client_code = self._generate_python_client_code(spec, config)
            with open(os.path.join(client_dir, "__init__.py"), "w") as f:
                f.write(client_code)

            # Generate models
            models_code = self._generate_python_models(spec)
            with open(os.path.join(client_dir, "models.py"), "w") as f:
                f.write(models_code)

            # Generate API classes
            api_code = self._generate_python_api_classes(spec)
            with open(os.path.join(client_dir, "api.py"), "w") as f:
                f.write(api_code)

            # Generate setup.py
            setup_code = self._generate_python_setup(config)
            with open(os.path.join(output_path, "setup.py"), "w") as f:
                f.write(setup_code)

            # Generate examples
            examples_dir = os.path.join(output_path, "examples")
            if self.include_examples:
                os.makedirs(examples_dir, exist_ok=True)
                examples_code = self._generate_python_examples(config)
                with open(os.path.join(examples_dir, "basic_usage.py"), "w") as f:
                    f.write(examples_code)

            # Generate requirements.txt
            with open(os.path.join(output_path, "requirements.txt"), "w") as f:
                f.write("requests>=2.25.0\ntyping-extensions>=3.7.4\n")

            # Generate README
            readme_content = self._generate_python_readme(config)
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

            if self.include_examples:
                files_generated.append("examples/basic_usage.py")

            return GeneratedClient(
                language=ClientLanguage.PYTHON,
                package_name=config.package_name,
                version=config.version,
                output_path=output_path,
                files_generated=files_generated,
                examples_included=self.include_examples,
                documentation_path=os.path.join(output_path, "README.md"),
                installation_instructions="pip install -e .",
            )

        except Exception as e:
            logger.error(f"Failed to generate Python client: {e}")
            raise

    async def _generate_javascript_client(
        self, config: ClientConfig, output_path: str
    ) -> GeneratedClient:
        """Generate JavaScript client library"""
        try:
            # Create JS client structure
            src_dir = os.path.join(output_path, "src")
            os.makedirs(src_dir, exist_ok=True)

            # Generate OpenAPI spec
            spec = self.get_openapi_spec()
            spec_file = os.path.join(output_path, "openapi.json")
            with open(spec_file, "w") as f:
                json.dump(spec, f, indent=2)

            # Generate main client file
            client_code = self._generate_javascript_client_code(spec, config)
            with open(os.path.join(src_dir, "mvidarr-client.js"), "w") as f:
                f.write(client_code)

            # Generate package.json
            package_json = self._generate_javascript_package_json(config)
            with open(os.path.join(output_path, "package.json"), "w") as f:
                json.dump(package_json, f, indent=2)

            # Generate examples
            if self.include_examples:
                examples_dir = os.path.join(output_path, "examples")
                os.makedirs(examples_dir, exist_ok=True)
                examples_code = self._generate_javascript_examples(config)
                with open(os.path.join(examples_dir, "basic-usage.js"), "w") as f:
                    f.write(examples_code)

            # Generate README
            readme_content = self._generate_javascript_readme(config)
            with open(os.path.join(output_path, "README.md"), "w") as f:
                f.write(readme_content)

            files_generated = ["src/mvidarr-client.js", "package.json", "README.md"]

            if self.include_examples:
                files_generated.append("examples/basic-usage.js")

            return GeneratedClient(
                language=ClientLanguage.JAVASCRIPT,
                package_name=config.package_name,
                version=config.version,
                output_path=output_path,
                files_generated=files_generated,
                examples_included=self.include_examples,
                documentation_path=os.path.join(output_path, "README.md"),
                installation_instructions="npm install",
            )

        except Exception as e:
            logger.error(f"Failed to generate JavaScript client: {e}")
            raise

    async def _generate_typescript_client(
        self, config: ClientConfig, output_path: str
    ) -> GeneratedClient:
        """Generate TypeScript client library"""
        try:
            # Create TS client structure
            src_dir = os.path.join(output_path, "src")
            os.makedirs(src_dir, exist_ok=True)

            # Generate OpenAPI spec
            spec = self.get_openapi_spec()

            # Generate TypeScript definitions
            types_code = self._generate_typescript_types(spec)
            with open(os.path.join(src_dir, "types.ts"), "w") as f:
                f.write(types_code)

            # Generate main client
            client_code = self._generate_typescript_client_code(spec, config)
            with open(os.path.join(src_dir, "client.ts"), "w") as f:
                f.write(client_code)

            # Generate index file
            index_code = self._generate_typescript_index()
            with open(os.path.join(src_dir, "index.ts"), "w") as f:
                f.write(index_code)

            # Generate package.json
            package_json = self._generate_typescript_package_json(config)
            with open(os.path.join(output_path, "package.json"), "w") as f:
                json.dump(package_json, f, indent=2)

            # Generate tsconfig.json
            tsconfig = self._generate_typescript_config()
            with open(os.path.join(output_path, "tsconfig.json"), "w") as f:
                json.dump(tsconfig, f, indent=2)

            # Generate examples
            if self.include_examples:
                examples_dir = os.path.join(output_path, "examples")
                os.makedirs(examples_dir, exist_ok=True)
                examples_code = self._generate_typescript_examples(config)
                with open(os.path.join(examples_dir, "basic-usage.ts"), "w") as f:
                    f.write(examples_code)

            files_generated = [
                "src/types.ts",
                "src/client.ts",
                "src/index.ts",
                "package.json",
                "tsconfig.json",
            ]

            if self.include_examples:
                files_generated.append("examples/basic-usage.ts")

            return GeneratedClient(
                language=ClientLanguage.TYPESCRIPT,
                package_name=config.package_name,
                version=config.version,
                output_path=output_path,
                files_generated=files_generated,
                examples_included=self.include_examples,
                documentation_path=os.path.join(output_path, "README.md"),
                installation_instructions="npm install && npm run build",
            )

        except Exception as e:
            logger.error(f"Failed to generate TypeScript client: {e}")
            raise

    async def _generate_openapi_client(
        self, config: ClientConfig, output_path: str
    ) -> GeneratedClient:
        """Generate client using OpenAPI Generator (for Java, Go, etc.)"""
        try:
            if not self.openapi_generator_jar:
                raise ValueError("OpenAPI Generator JAR path not configured")

            # Generate OpenAPI spec
            spec = self.get_openapi_spec()
            spec_file = os.path.join(output_path, "openapi.json")
            with open(spec_file, "w") as f:
                json.dump(spec, f, indent=2)

            # Prepare generator command
            generator_name = self._get_openapi_generator_name(config.language)

            cmd = [
                "java",
                "-jar",
                self.openapi_generator_jar,
                "generate",
                "-i",
                spec_file,
                "-g",
                generator_name,
                "-o",
                output_path,
            ]

            # Add additional properties
            for key, value in config.additional_properties.items():
                cmd.extend(["--additional-properties", f"{key}={value}"])

            # Run generator
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                raise RuntimeError(f"OpenAPI Generator failed: {result.stderr}")

            # Determine generated files (simplified)
            files_generated = ["Generated by OpenAPI Generator"]

            return GeneratedClient(
                language=config.language,
                package_name=config.package_name,
                version=config.version,
                output_path=output_path,
                files_generated=files_generated,
                examples_included=False,
                documentation_path=None,
                installation_instructions="See generated README",
            )

        except Exception as e:
            logger.error(f"Failed to generate OpenAPI client: {e}")
            raise

    async def _generate_custom_client(
        self, config: ClientConfig, output_path: str
    ) -> GeneratedClient:
        """Generate custom client for unsupported languages"""
        # Placeholder for custom client generation
        raise NotImplementedError(
            f"Custom client generation for {config.language.value} not implemented"
        )

    def _generate_python_client_code(
        self, spec: Dict[str, Any], config: ClientConfig
    ) -> str:
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

    def _generate_python_models(self, spec: Dict[str, Any]) -> str:
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

    def _generate_python_api_classes(self, spec: Dict[str, Any]) -> str:
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

    def _generate_python_setup(self, config: ClientConfig) -> str:
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

    def _generate_python_examples(self, config: ClientConfig) -> str:
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

    def _generate_python_readme(self, config: ClientConfig) -> str:
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

    def _generate_javascript_client_code(
        self, spec: Dict[str, Any], config: ClientConfig
    ) -> str:
        """Generate JavaScript client code"""
        return """/**
 * MVidarr JavaScript Client Library
 * Generated automatically from OpenAPI specification
 */

class MVidarrClient {
    constructor(baseUrl = 'http://localhost:5000', apiKey = null) {
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.apiKey = apiKey;
        
        // Default headers
        this.defaultHeaders = {
            'Content-Type': 'application/json',
            'User-Agent': 'MVidarr-JS-Client/1.0.0'
        };
        
        if (apiKey) {
            this.defaultHeaders['X-API-Key'] = apiKey;
        }
    }
    
    async _makeRequest(method, endpoint, options = {}) {
        const url = `${this.baseUrl}${endpoint}`;
        
        const config = {
            method,
            headers: { ...this.defaultHeaders, ...options.headers },
            ...options
        };
        
        if (options.data) {
            config.body = JSON.stringify(options.data);
        }
        
        try {
            const response = await fetch(url, config);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            return await response.json();
        } catch (error) {
            throw new Error(`API request failed: ${error.message}`);
        }
    }
    
    // Videos API
    async getVideos(page = 1, perPage = 50) {
        const params = new URLSearchParams({ page, per_page: perPage });
        return this._makeRequest('GET', `/api/videos?${params}`);
    }
    
    async getVideo(videoId) {
        return this._makeRequest('GET', `/api/videos/${videoId}`);
    }
    
    async createVideo(videoData) {
        return this._makeRequest('POST', '/api/videos', { data: videoData });
    }
    
    async updateVideo(videoId, videoData) {
        return this._makeRequest('PUT', `/api/videos/${videoId}`, { data: videoData });
    }
    
    async deleteVideo(videoId) {
        return this._makeRequest('DELETE', `/api/videos/${videoId}`);
    }
    
    // Artists API
    async getArtists(page = 1, perPage = 50) {
        const params = new URLSearchParams({ page, per_page: perPage });
        return this._makeRequest('GET', `/api/artists?${params}`);
    }
    
    async getArtist(artistId) {
        return this._makeRequest('GET', `/api/artists/${artistId}`);
    }
    
    // Playlists API
    async getPlaylists() {
        return this._makeRequest('GET', '/api/playlists');
    }
    
    async createPlaylist(playlistData) {
        return this._makeRequest('POST', '/api/playlists', { data: playlistData });
    }
}

// Export for different module systems
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MVidarrClient;
} else if (typeof window !== 'undefined') {
    window.MVidarrClient = MVidarrClient;
}
"""

    def _generate_javascript_package_json(self, config: ClientConfig) -> Dict[str, Any]:
        """Generate JavaScript package.json"""
        return {
            "name": config.package_name,
            "version": config.version,
            "description": config.description,
            "main": "src/mvidarr-client.js",
            "author": config.author,
            "license": config.license,
            "keywords": ["mvidarr", "api", "client", "music", "video"],
            "repository": {
                "type": "git",
                "url": "https://github.com/prefect421/mvidarr-js-client",
            },
            "scripts": {"test": 'echo "Error: no test specified" && exit 1'},
        }

    def _generate_javascript_examples(self, config: ClientConfig) -> str:
        """Generate JavaScript usage examples"""
        return """/**
 * MVidarr JavaScript Client - Basic Usage Examples
 */

const MVidarrClient = require('../src/mvidarr-client');

// Initialize client
const client = new MVidarrClient('http://localhost:5000');

async function basicUsage() {
    try {
        // Get videos
        console.log('Fetching videos...');
        const videos = await client.getVideos(1, 10);
        console.log(`Found ${videos.videos?.length || 0} videos`);
        
        // Get specific video
        if (videos.videos && videos.videos.length > 0) {
            const video = await client.getVideo(videos.videos[0].id);
            console.log(`Video: ${video.title}`);
        }
        
        // Get artists
        console.log('\\nFetching artists...');
        const artists = await client.getArtists();
        console.log(`Found ${artists.artists?.length || 0} artists`);
        
        // Get playlists
        console.log('\\nFetching playlists...');
        const playlists = await client.getPlaylists();
        console.log(`Found ${playlists.playlists?.length || 0} playlists`);
        
    } catch (error) {
        console.error('Error:', error.message);
    }
}

// Run examples
basicUsage();
"""

    def _generate_javascript_readme(self, config: ClientConfig) -> str:
        """Generate JavaScript README"""
        return f"""# {config.package_name}

{config.description}

## Installation

```bash
npm install
```

## Quick Start

```javascript
const MVidarrClient = require('{config.package_name}');

// Initialize client
const client = new MVidarrClient('http://localhost:5000');

// Get videos
client.getVideos().then(videos => {{
    console.log(`Found ${{videos.videos.length}} videos`);
}});

// Get artists
client.getArtists().then(artists => {{
    console.log(`Found ${{artists.artists.length}} artists`);
}});
```

## Browser Usage

```html
<script src="src/mvidarr-client.js"></script>
<script>
    const client = new MVidarrClient('http://localhost:5000');
    
    client.getVideos().then(videos => {{
        console.log('Videos:', videos);
    }});
</script>
```

## API Documentation

For complete API documentation, see the [MVidarr API Documentation](http://localhost:5000/docs).

## License

{config.license}
"""

    def _generate_typescript_types(self, spec: Dict[str, Any]) -> str:
        """Generate TypeScript type definitions"""
        return """/**
 * MVidarr API TypeScript Definitions
 */

export interface Video {
    id: number;
    title: string;
    artist_id?: number;
    artist_name?: string;
    duration?: number;
    file_path?: string;
    thumbnail_path?: string;
    created_at?: string;
    updated_at?: string;
}

export interface Artist {
    id: number;
    name: string;
    description?: string;
    created_at?: string;
    updated_at?: string;
}

export interface Playlist {
    id: number;
    name: string;
    description?: string;
    user_id?: number;
    created_at?: string;
    updated_at?: string;
}

export interface APIResponse<T> {
    data: T;
    meta?: {
        api_version: string;
        timestamp: string;
        pagination?: {
            page: number;
            per_page: number;
            total: number;
            pages: number;
        };
    };
}

export interface VideoListResponse {
    videos: Video[];
    total: number;
    page: number;
    per_page: number;
    pages: number;
}

export interface ArtistListResponse {
    artists: Artist[];
    total: number;
    page: number;
    per_page: number;
    pages: number;
}

export interface ClientConfig {
    baseUrl?: string;
    apiKey?: string;
    timeout?: number;
}
"""

    def _generate_typescript_client_code(
        self, spec: Dict[str, Any], config: ClientConfig
    ) -> str:
        """Generate TypeScript client code"""
        return """/**
 * MVidarr TypeScript Client Library
 */

import { Video, Artist, Playlist, VideoListResponse, ArtistListResponse, ClientConfig } from './types';

export class MVidarrClient {
    private baseUrl: string;
    private apiKey?: string;
    private timeout: number;

    constructor(config: ClientConfig = {}) {
        this.baseUrl = (config.baseUrl || 'http://localhost:5000').replace(/\/$/, '');
        this.apiKey = config.apiKey;
        this.timeout = config.timeout || 10000;
    }

    private async makeRequest<T>(
        method: string,
        endpoint: string,
        options: RequestInit = {}
    ): Promise<T> {
        const url = `${this.baseUrl}${endpoint}`;
        
        const headers: HeadersInit = {
            'Content-Type': 'application/json',
            'User-Agent': 'MVidarr-TS-Client/1.0.0',
            ...options.headers,
        };

        if (this.apiKey) {
            headers['X-API-Key'] = this.apiKey;
        }

        const config: RequestInit = {
            method,
            headers,
            ...options,
        };

        if (options.body && typeof options.body === 'object') {
            config.body = JSON.stringify(options.body);
        }

        try {
            const response = await fetch(url, config);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            return await response.json();
        } catch (error) {
            throw new Error(`API request failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
        }
    }

    // Videos API
    async getVideos(page: number = 1, perPage: number = 50): Promise<VideoListResponse> {
        const params = new URLSearchParams({
            page: page.toString(),
            per_page: perPage.toString()
        });
        return this.makeRequest<VideoListResponse>('GET', `/api/videos?${params}`);
    }

    async getVideo(videoId: number): Promise<Video> {
        return this.makeRequest<Video>('GET', `/api/videos/${videoId}`);
    }

    async createVideo(videoData: Partial<Video>): Promise<Video> {
        return this.makeRequest<Video>('POST', '/api/videos', { body: videoData });
    }

    async updateVideo(videoId: number, videoData: Partial<Video>): Promise<Video> {
        return this.makeRequest<Video>('PUT', `/api/videos/${videoId}`, { body: videoData });
    }

    async deleteVideo(videoId: number): Promise<void> {
        await this.makeRequest<void>('DELETE', `/api/videos/${videoId}`);
    }

    // Artists API
    async getArtists(page: number = 1, perPage: number = 50): Promise<ArtistListResponse> {
        const params = new URLSearchParams({
            page: page.toString(),
            per_page: perPage.toString()
        });
        return this.makeRequest<ArtistListResponse>('GET', `/api/artists?${params}`);
    }

    async getArtist(artistId: number): Promise<Artist> {
        return this.makeRequest<Artist>('GET', `/api/artists/${artistId}`);
    }

    // Playlists API
    async getPlaylists(): Promise<{ playlists: Playlist[] }> {
        return this.makeRequest<{ playlists: Playlist[] }>('GET', '/api/playlists');
    }

    async createPlaylist(playlistData: Partial<Playlist>): Promise<Playlist> {
        return this.makeRequest<Playlist>('POST', '/api/playlists', { body: playlistData });
    }
}
"""

    def _generate_typescript_index(self) -> str:
        """Generate TypeScript index file"""
        return """/**
 * MVidarr TypeScript Client - Main Export
 */

export { MVidarrClient } from './client';
export * from './types';
"""

    def _generate_typescript_package_json(self, config: ClientConfig) -> Dict[str, Any]:
        """Generate TypeScript package.json"""
        return {
            "name": config.package_name,
            "version": config.version,
            "description": config.description,
            "main": "dist/index.js",
            "types": "dist/index.d.ts",
            "author": config.author,
            "license": config.license,
            "keywords": ["mvidarr", "api", "client", "music", "video", "typescript"],
            "scripts": {
                "build": "tsc",
                "dev": "tsc --watch",
                "prepublishOnly": "npm run build",
            },
            "devDependencies": {"typescript": "^4.9.0", "@types/node": "^18.0.0"},
            "files": ["dist/**/*"],
        }

    def _generate_typescript_config(self) -> Dict[str, Any]:
        """Generate TypeScript configuration"""
        return {
            "compilerOptions": {
                "target": "ES2018",
                "module": "commonjs",
                "lib": ["ES2018", "DOM"],
                "outDir": "./dist",
                "rootDir": "./src",
                "declaration": True,
                "declarationMap": True,
                "sourceMap": True,
                "strict": True,
                "esModuleInterop": True,
                "skipLibCheck": True,
                "forceConsistentCasingInFileNames": True,
            },
            "include": ["src/**/*"],
            "exclude": ["node_modules", "dist", "examples"],
        }

    def _generate_typescript_examples(self, config: ClientConfig) -> str:
        """Generate TypeScript usage examples"""
        return """/**
 * MVidarr TypeScript Client - Basic Usage Examples
 */

import { MVidarrClient, Video, Artist } from '../src';

// Initialize client
const client = new MVidarrClient({
    baseUrl: 'http://localhost:5000',
    timeout: 10000
});

async function basicUsage(): Promise<void> {
    try {
        // Get videos with type safety
        console.log('Fetching videos...');
        const videosResponse = await client.getVideos(1, 10);
        console.log(`Found ${videosResponse.videos.length} videos`);

        // Get specific video
        if (videosResponse.videos.length > 0) {
            const video: Video = await client.getVideo(videosResponse.videos[0].id);
            console.log(`Video: ${video.title}`);
        }

        // Get artists
        console.log('\\nFetching artists...');
        const artistsResponse = await client.getArtists();
        console.log(`Found ${artistsResponse.artists.length} artists`);

        // Create new video with type checking
        const newVideo: Partial<Video> = {
            title: 'New Video',
            artist_name: 'Test Artist'
        };
        
        const createdVideo = await client.createVideo(newVideo);
        console.log(`Created video with ID: ${createdVideo.id}`);

    } catch (error) {
        console.error('Error:', error instanceof Error ? error.message : 'Unknown error');
    }
}

// Run examples
basicUsage();
"""

    def _get_openapi_generator_name(self, language: ClientLanguage) -> str:
        """Get OpenAPI generator name for language"""
        generator_names = {
            ClientLanguage.JAVA: "java",
            ClientLanguage.GO: "go",
            ClientLanguage.CSHARP: "csharp",
            ClientLanguage.PHP: "php",
            ClientLanguage.RUBY: "ruby",
            ClientLanguage.SWIFT: "swift",
            ClientLanguage.RUST: "rust",
        }
        return generator_names.get(language, language.value)


# Global generator instance
_client_generator = None


def get_client_generator(
    app: FastAPI, config: Optional[Dict] = None
) -> ClientLibraryGenerator:
    """Get global client generator instance"""
    global _client_generator

    if _client_generator is None:
        _client_generator = ClientLibraryGenerator(app, config)

    return _client_generator
