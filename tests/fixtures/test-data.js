// tests/fixtures/test-data.js

/**
 * Test data fixtures for MVidarr E2E tests
 */

// Test user accounts
const testUsers = {
  admin: {
    username: 'admin',
    password: 'admin123',
    email: 'admin@mvidarr.test'
  },
  user: {
    username: 'testuser',
    password: 'testpass',
    email: 'user@mvidarr.test'
  }
};

// Test artist data
const testArtists = {
  taylorSwift: {
    name: 'Taylor Swift',
    imvdb_id: 'test_taylor_swift',
    genres: ['Pop', 'Country'],
    auto_download: true
  },
  beatles: {
    name: 'The Beatles',
    imvdb_id: 'test_beatles',
    genres: ['Rock', 'Pop'],
    auto_download: false
  },
  eminem: {
    name: 'Eminem',
    imvdb_id: 'test_eminem',
    genres: ['Hip-Hop', 'Rap'],
    auto_download: true
  }
};

// Test video data
const testVideos = {
  badBlood: {
    title: 'Bad Blood',
    artist: 'Taylor Swift',
    year: 2015,
    url: 'https://youtube.com/watch?v=QcIy9NiNbmo',
    imvdb_id: 'test_bad_blood'
  },
  heyJude: {
    title: 'Hey Jude',
    artist: 'The Beatles',
    year: 1968,
    url: 'https://youtube.com/watch?v=A_MjCqQoLLA',
    imvdb_id: 'test_hey_jude'
  },
  loseYourself: {
    title: 'Lose Yourself',
    artist: 'Eminem',
    year: 2002,
    url: 'https://youtube.com/watch?v=_Yhyp-_hX2s',
    imvdb_id: 'test_lose_yourself'
  }
};

// Test playlist data
const testPlaylists = {
  topHits: {
    name: 'Top Hits 2024',
    url: 'https://youtube.com/playlist?list=PLtest123',
    description: 'Best music videos of 2024'
  },
  classics: {
    name: 'Classic Rock',
    url: 'https://youtube.com/playlist?list=PLtest456',
    description: 'Timeless rock music videos'
  }
};

// Mock API responses
const mockResponses = {
  imvdbArtistSearch: {
    success: true,
    results: [
      {
        id: 'mock_artist_1',
        name: 'Test Artist 1',
        thumbnail: 'https://example.com/thumb1.jpg',
        video_count: 15
      },
      {
        id: 'mock_artist_2', 
        name: 'Test Artist 2',
        thumbnail: 'https://example.com/thumb2.jpg',
        video_count: 8
      }
    ],
    total: 2
  },
  
  imvdbVideoSearch: {
    success: true,
    results: [
      {
        id: 'mock_video_1',
        title: 'Test Video 1',
        artist: 'Test Artist',
        year: 2023,
        thumbnail: 'https://example.com/video1.jpg'
      },
      {
        id: 'mock_video_2',
        title: 'Test Video 2', 
        artist: 'Test Artist',
        year: 2023,
        thumbnail: 'https://example.com/video2.jpg'
      }
    ],
    total: 2
  },

  dashboardStats: {
    artists_count: 25,
    videos_count: 150,
    downloads_count: 5,
    storage_used: '2.5 GB'
  },

  downloadQueue: {
    queue: [
      {
        id: 1,
        title: 'Test Download 1',
        artist: 'Test Artist',
        status: 'queued',
        progress: 0
      }
    ],
    total: 1
  }
};

// Test form data
const testForms = {
  addArtist: {
    name: 'New Test Artist',
    auto_download: true,
    genres: ['Pop', 'Rock']
  },
  
  addVideo: {
    title: 'New Test Video',
    artist: 'Test Artist',
    url: 'https://youtube.com/watch?v=test123'
  },
  
  settings: {
    app_name: 'MVidarr Test',
    max_download_quality: '1080p',
    auto_discovery: true
  }
};

// Error scenarios for testing
const errorScenarios = {
  networkError: {
    message: 'Network request failed',
    code: 'NETWORK_ERROR'
  },
  
  authenticationError: {
    message: 'Authentication failed',
    code: 'AUTH_ERROR'
  },
  
  validationError: {
    message: 'Invalid input data',
    code: 'VALIDATION_ERROR'
  }
};

module.exports = {
  testUsers,
  testArtists,
  testVideos,
  testPlaylists,
  mockResponses,
  testForms,
  errorScenarios
};