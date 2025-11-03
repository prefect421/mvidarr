"""
JavaScript Client Library Generation - Issue 128 Advanced FastAPI Features
Functions for generating JavaScript client libraries
"""

import json
import os
from typing import Any, Dict

from src.api.fastapi.client_models import ClientConfig, ClientLanguage, GeneratedClient
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.client_javascript_generator")


async def generate_javascript_client(
    spec: Dict[str, Any],
    config: ClientConfig,
    output_path: str,
    include_examples: bool = True,
) -> GeneratedClient:
    """Generate JavaScript client library"""
    try:
        # Create JS client structure
        src_dir = os.path.join(output_path, "src")
        os.makedirs(src_dir, exist_ok=True)

        # Generate OpenAPI spec
        spec_file = os.path.join(output_path, "openapi.json")
        with open(spec_file, "w") as f:
            json.dump(spec, f, indent=2)

        # Generate main client file
        client_code = generate_javascript_client_code(spec, config)
        with open(os.path.join(src_dir, "mvidarr-client.js"), "w") as f:
            f.write(client_code)

        # Generate package.json
        package_json = generate_javascript_package_json(config)
        with open(os.path.join(output_path, "package.json"), "w") as f:
            json.dump(package_json, f, indent=2)

        # Generate examples
        if include_examples:
            examples_dir = os.path.join(output_path, "examples")
            os.makedirs(examples_dir, exist_ok=True)
            examples_code = generate_javascript_examples(config)
            with open(os.path.join(examples_dir, "basic-usage.js"), "w") as f:
                f.write(examples_code)

        # Generate README
        readme_content = generate_javascript_readme(config)
        with open(os.path.join(output_path, "README.md"), "w") as f:
            f.write(readme_content)

        files_generated = ["src/mvidarr-client.js", "package.json", "README.md"]

        if include_examples:
            files_generated.append("examples/basic-usage.js")

        return GeneratedClient(
            language=ClientLanguage.JAVASCRIPT,
            package_name=config.package_name,
            version=config.version,
            output_path=output_path,
            files_generated=files_generated,
            examples_included=include_examples,
            documentation_path=os.path.join(output_path, "README.md"),
            installation_instructions="npm install",
        )

    except Exception as e:
        logger.error(f"Failed to generate JavaScript client: {e}")
        raise


def generate_javascript_client_code(spec: Dict[str, Any], config: ClientConfig) -> str:
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


def generate_javascript_package_json(config: ClientConfig) -> Dict[str, Any]:
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


def generate_javascript_examples(config: ClientConfig) -> str:
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


def generate_javascript_readme(config: ClientConfig) -> str:
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
