"""
TypeScript Client Library Generation - Issue 128 Advanced FastAPI Features
Functions for generating TypeScript client libraries
"""

import json
import os
from typing import Any, Dict

from src.api.fastapi.client_models import ClientConfig, ClientLanguage, GeneratedClient
from src.utils.logger import get_logger

logger = get_logger("mvidarr.api.client_typescript_generator")


async def generate_typescript_client(
    spec: Dict[str, Any],
    config: ClientConfig,
    output_path: str,
    include_examples: bool = True,
) -> GeneratedClient:
    """Generate TypeScript client library"""
    try:
        # Create TS client structure
        src_dir = os.path.join(output_path, "src")
        os.makedirs(src_dir, exist_ok=True)

        # Generate TypeScript definitions
        types_code = generate_typescript_types(spec)
        with open(os.path.join(src_dir, "types.ts"), "w") as f:
            f.write(types_code)

        # Generate main client
        client_code = generate_typescript_client_code(spec, config)
        with open(os.path.join(src_dir, "client.ts"), "w") as f:
            f.write(client_code)

        # Generate index file
        index_code = generate_typescript_index()
        with open(os.path.join(src_dir, "index.ts"), "w") as f:
            f.write(index_code)

        # Generate package.json
        package_json = generate_typescript_package_json(config)
        with open(os.path.join(output_path, "package.json"), "w") as f:
            json.dump(package_json, f, indent=2)

        # Generate tsconfig.json
        tsconfig = generate_typescript_config()
        with open(os.path.join(output_path, "tsconfig.json"), "w") as f:
            json.dump(tsconfig, f, indent=2)

        # Generate examples
        if include_examples:
            examples_dir = os.path.join(output_path, "examples")
            os.makedirs(examples_dir, exist_ok=True)
            examples_code = generate_typescript_examples(config)
            with open(os.path.join(examples_dir, "basic-usage.ts"), "w") as f:
                f.write(examples_code)

        files_generated = [
            "src/types.ts",
            "src/client.ts",
            "src/index.ts",
            "package.json",
            "tsconfig.json",
        ]

        if include_examples:
            files_generated.append("examples/basic-usage.ts")

        return GeneratedClient(
            language=ClientLanguage.TYPESCRIPT,
            package_name=config.package_name,
            version=config.version,
            output_path=output_path,
            files_generated=files_generated,
            examples_included=include_examples,
            documentation_path=os.path.join(output_path, "README.md"),
            installation_instructions="npm install && npm run build",
        )

    except Exception as e:
        logger.error(f"Failed to generate TypeScript client: {e}")
        raise


def generate_typescript_types(spec: Dict[str, Any]) -> str:
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


def generate_typescript_client_code(spec: Dict[str, Any], config: ClientConfig) -> str:
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


def generate_typescript_index() -> str:
    """Generate TypeScript index file"""
    return """/**
 * MVidarr TypeScript Client - Main Export
 */

export { MVidarrClient } from './client';
export * from './types';
"""


def generate_typescript_package_json(config: ClientConfig) -> Dict[str, Any]:
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


def generate_typescript_config() -> Dict[str, Any]:
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


def generate_typescript_examples(config: ClientConfig) -> str:
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
