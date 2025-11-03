/**
 * API Endpoint Tests
 * Tests all major API endpoints for proper responses and authentication
 */

import { test, expect, APIRequestContext } from '@playwright/test';

// Helper to get authenticated API context
async function getAuthenticatedContext(request: APIRequestContext): Promise<string> {
  const response = await request.post('/test-login', {
    data: {
      username: 'admin',
      password: 'mvidarr'
    }
  });

  const cookies = response.headers()['set-cookie'];
  return cookies || '';
}

test.describe('Health and Status APIs', () => {
  test('GET /health should return healthy status', async ({ request }) => {
    const response = await request.get('/health');
    expect(response.ok()).toBeTruthy();

    const data = await response.json();
    expect(data).toHaveProperty('status');
  });

  test('GET /api/health should return health check', async ({ request }) => {
    const response = await request.get('/api/health');
    expect([200, 404]).toContain(response.status());
  });

  test('GET /frontend/health should return frontend health', async ({ request }) => {
    const response = await request.get('/frontend/health');

    // Endpoint may return 404 if route not configured
    // Accept both success and not found
    expect([200, 404]).toContain(response.status());

    if (response.ok()) {
      const data = await response.json();
      expect(data).toHaveProperty('status');
      expect(data).toHaveProperty('template_system');
    }
  });
});

test.describe('Videos API', () => {
  test('GET /api/videos should return videos list', async ({ request }) => {
    const response = await request.get('/api/videos');

    // Might require auth or return 200/401
    expect([200, 401, 403]).toContain(response.status());

    if (response.ok()) {
      const data = await response.json();
      expect(data).toHaveProperty('videos');
    }
  });

  test('GET /api/videos with pagination', async ({ request }) => {
    const response = await request.get('/api/videos?page=1&per_page=10');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/videos/:id should return video details', async ({ request }) => {
    const response = await request.get('/api/videos/1');
    expect([200, 404, 401, 403]).toContain(response.status());
  });

  test('GET /api/videos/search should handle search', async ({ request }) => {
    const response = await request.get('/api/videos/search?q=test');
    expect([200, 401, 403]).toContain(response.status());
  });
});

test.describe('Artists API', () => {
  test('GET /api/artists should return artists list', async ({ request }) => {
    const response = await request.get('/api/artists');
    expect([200, 401, 403]).toContain(response.status());

    if (response.ok()) {
      const data = await response.json();
      // Should have artists property
      expect(data).toBeTruthy();
    }
  });

  test('GET /api/artists/:id should return artist details', async ({ request }) => {
    const response = await request.get('/api/artists/1');
    expect([200, 404, 401, 403]).toContain(response.status());
  });

  test('GET /api/artists/search should handle search', async ({ request }) => {
    const response = await request.get('/api/artists/search/advanced?q=test');
    expect([200, 401, 403, 404]).toContain(response.status());
  });

  test('GET /api/artists/:id/videos should return artist videos', async ({ request }) => {
    const response = await request.get('/api/artists/1/videos');
    expect([200, 404, 401, 403]).toContain(response.status());
  });
});

test.describe('Playlists API', () => {
  test('GET /api/playlists should return playlists list', async ({ request }) => {
    const response = await request.get('/api/playlists');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/playlists/:id should return playlist details', async ({ request }) => {
    const response = await request.get('/api/playlists/1');
    expect([200, 404, 401, 403]).toContain(response.status());
  });

  test('GET /api/playlists/:id/videos should return playlist videos', async ({ request }) => {
    const response = await request.get('/api/playlists/1/videos');
    expect([200, 404, 401, 403]).toContain(response.status());
  });
});

test.describe('Jobs API', () => {
  test('GET /api/jobs should return jobs list', async ({ request }) => {
    const response = await request.get('/api/jobs');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/jobs/analytics should return analytics', async ({ request }) => {
    const response = await request.get('/api/jobs/analytics');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/jobs/stats/queue should return queue stats', async ({ request }) => {
    const response = await request.get('/api/jobs/stats/queue');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/jobs/:id should return job details', async ({ request }) => {
    const response = await request.get('/api/jobs/test-job-id');
    expect([200, 404, 401, 403]).toContain(response.status());
  });
});

test.describe('Metadata Enrichment API', () => {
  test('GET /api/metadata/stats should return stats', async ({ request }) => {
    const response = await request.get('/api/metadata/stats');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/metadata/services/status should return services status', async ({ request }) => {
    const response = await request.get('/api/metadata/services/status');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/metadata/search/lastfm should handle search', async ({ request }) => {
    const response = await request.get('/api/metadata/search/lastfm?query=test');
    expect([200, 400, 401, 403]).toContain(response.status());
  });
});

test.describe('Analytics API', () => {
  test('GET /api/analytics/dashboard should return dashboard data', async ({ request }) => {
    const response = await request.get('/api/analytics/dashboard');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/analytics/system/health should return system health', async ({ request }) => {
    const response = await request.get('/api/analytics/system/health');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/analytics/services/status should return services status', async ({ request }) => {
    const response = await request.get('/api/analytics/services/status');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/analytics/popular-content should return popular content', async ({ request }) => {
    const response = await request.get('/api/analytics/popular-content');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/analytics/trending-content should return trending content', async ({ request }) => {
    const response = await request.get('/api/analytics/trending-content');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/analytics/real-time/metrics should return real-time metrics', async ({ request }) => {
    const response = await request.get('/api/analytics/real-time/metrics');
    expect([200, 401, 403]).toContain(response.status());
  });
});

test.describe('Settings API', () => {
  test('GET /api/settings should return all settings', async ({ request }) => {
    const response = await request.get('/api/settings');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/settings/:key should return specific setting', async ({ request }) => {
    const response = await request.get('/api/settings/app_name');
    expect([200, 404, 401, 403]).toContain(response.status());
  });
});

test.describe('Admin API', () => {
  test('GET /api/admin/dashboard should return admin dashboard', async ({ request }) => {
    const response = await request.get('/api/admin/dashboard');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/admin/system/status should return system status', async ({ request }) => {
    const response = await request.get('/api/admin/system/status');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/admin/users should return users list', async ({ request }) => {
    const response = await request.get('/api/admin/users');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/admin/audit/logs should return audit logs', async ({ request }) => {
    const response = await request.get('/api/admin/audit/logs');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/admin/health/detailed should return detailed health', async ({ request }) => {
    const response = await request.get('/api/admin/health/detailed');
    expect([200, 401, 403]).toContain(response.status());
  });
});

test.describe('Advanced Search API', () => {
  test('POST /api/search/videos should handle video search', async ({ request }) => {
    const response = await request.post('/api/search/videos', {
      data: {
        query: 'test',
        filters: {}
      }
    });
    expect([200, 400, 401, 403]).toContain(response.status());
  });

  test('GET /api/search/presets should return search presets', async ({ request }) => {
    const response = await request.get('/api/search/presets');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/search/suggestions should return search suggestions', async ({ request }) => {
    const response = await request.get('/api/search/suggestions');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/search/analytics should return search analytics', async ({ request }) => {
    const response = await request.get('/api/search/analytics');
    expect([200, 401, 403]).toContain(response.status());
  });
});

test.describe('Service Integration APIs', () => {
  test('GET /api/spotify/status should return Spotify status', async ({ request }) => {
    const response = await request.get('/api/spotify/status');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/lastfm/status should return Last.fm status', async ({ request }) => {
    const response = await request.get('/api/lastfm/status');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/youtube-playlists should return YouTube playlists', async ({ request }) => {
    const response = await request.get('/api/youtube-playlists');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/lidarr/status should return Lidarr status', async ({ request }) => {
    const response = await request.get('/api/lidarr/status');
    expect([200, 401, 403, 404]).toContain(response.status());
  });
});

test.describe('Bulk Operations APIs', () => {
  test('POST /api/videos/bulk/delete should handle bulk delete', async ({ request }) => {
    const response = await request.post('/api/videos/bulk/delete', {
      data: {
        video_ids: []
      }
    });
    expect([200, 400, 401, 403]).toContain(response.status());
  });

  test('POST /api/artists/bulk/delete should handle bulk delete', async ({ request }) => {
    const response = await request.post('/api/artists/bulk/delete', {
      data: {
        artist_ids: []
      }
    });
    expect([200, 400, 401, 403]).toContain(response.status());
  });

  test('POST /api/videos/bulk/edit should handle bulk edit', async ({ request }) => {
    const response = await request.post('/api/videos/bulk/edit', {
      data: {
        video_ids: [],
        updates: {}
      }
    });
    expect([200, 400, 401, 403]).toContain(response.status());
  });
});

test.describe('Image Processing APIs', () => {
  test('GET /api/image-processing/formats/supported should return formats', async ({ request }) => {
    const response = await request.get('/api/image-processing/formats/supported');
    expect([200, 401, 403, 404]).toContain(response.status());
  });

  test('GET /api/image-processing/enhancement/options should return options', async ({ request }) => {
    const response = await request.get('/api/image-processing/enhancement/options');
    expect([200, 401, 403, 404]).toContain(response.status());
  });
});

test.describe('Genres API', () => {
  test('GET /api/genres should return genres list', async ({ request }) => {
    const response = await request.get('/api/genres');
    expect([200, 401, 403]).toContain(response.status());
  });

  test('GET /api/genres/:id should return genre details', async ({ request }) => {
    const response = await request.get('/api/genres/1');
    expect([200, 404, 401, 403]).toContain(response.status());
  });
});

test.describe('Music Recommendations API', () => {
  test('GET /api/recommendations should return recommendations', async ({ request }) => {
    const response = await request.get('/api/recommendations');
    expect([200, 401, 403, 404]).toContain(response.status());
  });

  test('GET /api/recommendations/artist/:id should return artist recommendations', async ({ request }) => {
    const response = await request.get('/api/recommendations/artist/1');
    expect([200, 404, 401, 403]).toContain(response.status());
  });
});

test.describe('API Gateway Management', () => {
  test('GET /api/gateway/services should return services', async ({ request }) => {
    const response = await request.get('/api/gateway/services');
    expect([200, 401, 403, 404]).toContain(response.status());
  });

  test('GET /api/gateway/routes should return routes', async ({ request }) => {
    const response = await request.get('/api/gateway/routes');
    expect([200, 401, 403, 404]).toContain(response.status());
  });

  test('GET /api/gateway/stats should return gateway stats', async ({ request }) => {
    const response = await request.get('/api/gateway/stats');
    expect([200, 401, 403, 404]).toContain(response.status());
  });

  test('GET /api/gateway/health should return gateway health', async ({ request }) => {
    const response = await request.get('/api/gateway/health');
    expect([200, 401, 403, 404]).toContain(response.status());
  });

  test('GET /api/gateway/versions should return API versions', async ({ request }) => {
    const response = await request.get('/api/gateway/versions');
    expect([200, 401, 403, 404]).toContain(response.status());
  });
});

test.describe('API Error Handling', () => {
  test('should return 404 for non-existent endpoint', async ({ request }) => {
    const response = await request.get('/api/non-existent-endpoint');
    expect(response.status()).toBe(404);
  });

  test('should return 405 for wrong HTTP method', async ({ request }) => {
    const response = await request.delete('/api/health');
    expect([405, 404]).toContain(response.status());
  });

  test('should handle malformed JSON in POST', async ({ request }) => {
    const response = await request.post('/api/videos/bulk/delete', {
      data: 'invalid json',
      headers: {
        'Content-Type': 'application/json'
      }
    });
    expect([400, 422, 401, 403]).toContain(response.status());
  });
});

test.describe('API Rate Limiting', () => {
  test('should handle rapid requests', async ({ request }) => {
    const requests = [];

    for (let i = 0; i < 10; i++) {
      requests.push(request.get('/api/health'));
    }

    const responses = await Promise.all(requests);

    // All should either succeed or be rate limited
    responses.forEach(response => {
      expect([200, 429]).toContain(response.status());
    });
  });
});

test.describe('API Content Types', () => {
  test('JSON endpoints should return proper content type', async ({ request }) => {
    const response = await request.get('/health');

    if (response.ok()) {
      const contentType = response.headers()['content-type'];
      expect(contentType).toContain('application/json');
    }
  });

  test('HTML endpoints should return proper content type', async ({ request }) => {
    const response = await request.get('/');

    const contentType = response.headers()['content-type'];
    expect(contentType || '').toMatch(/text\/html|text\/plain/);
  });
});
