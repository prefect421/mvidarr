# Build Process Documentation

## Overview

This document covers the complete build process for MVidarr, including local development builds, production Docker builds, and CI/CD pipeline configurations. The build system has been optimized for reliability, speed, and maintainability.

## Development Build Process

### Prerequisites
```bash
# Python 3.12+ required
python --version  # Should be 3.12+

# Install development dependencies
pip install -r requirements-dev.txt

# Install runtime dependencies (requirements-prod.txt no longer exists as of
# v0.12.7 - folded into requirements.txt + requirements-fastapi.txt)
pip install -r requirements.txt -r requirements-fastapi.txt
```

### Code Quality and Formatting
Before any build, ensure code quality:

```bash
# Format Python code (exact version required for CI compatibility)
~/.local/bin/black --check src/
~/.local/bin/isort --profile black --check-only src/

# Auto-format if needed
~/.local/bin/black src/
~/.local/bin/isort --profile black src/
```

### Local Development Server
```bash
# Development mode - tables/migrations run automatically on startup
python fastapi_app.py

# Dev-only interactive API docs (Swagger/ReDoc) are enabled by MVIDARR_ENV=dev
MVIDARR_ENV=dev python fastapi_app.py
```

### Running Tests
```bash
# Run the test suite
pytest tests/ -v

# With coverage
pytest tests/ --cov=src
```

## Production Docker Build Process

### Multi-Stage Build Architecture

The production build uses a highly optimized multi-stage Dockerfile (`Dockerfile.production`) that separates build and runtime environments for maximum efficiency.

#### Stage 1: Builder Environment
```dockerfile
FROM python:3.12-slim AS builder
```

**Purpose**: Compile dependencies with all necessary build tools
**Contains**: gcc, g++, pkg-config, build tools, source compilation
**Excluded from final image**: Reduces security surface and image size

#### Stage 2: Runtime Environment  
```dockerfile
FROM python:3.12-slim AS runtime
```

**Purpose**: Lean production environment with only runtime dependencies
**Contains**: Application code, runtime libraries, minimal system packages
**Optimizations**: No build tools, optimized layer caching, security hardening

### Build Commands

#### Standard Production Build
```bash
# Build production image
docker build -f Dockerfile.production -t mvidarr:latest .

# Build with BuildKit optimization (recommended)
export DOCKER_BUILDKIT=1
docker build -f Dockerfile.production -t mvidarr:latest .
```

#### Build with Caching
```bash
# Build with registry cache
docker build -f Dockerfile.production \
  --cache-from ghcr.io/prefect421/mvidarr:cache \
  --cache-to ghcr.io/prefect421/mvidarr:cache \
  -t mvidarr:latest .
```

#### Multi-Platform Build
```bash
# Build for multiple architectures
docker buildx create --use
docker buildx build -f Dockerfile.production \
  --platform linux/amd64,linux/arm64 \
  -t ghcr.io/prefect421/mvidarr:latest \
  --push .
```

### Build Optimization Features

#### Layer Caching Strategy
```dockerfile
# 1. System dependencies (cached - rarely change)
RUN apt-get update && apt-get install...

# 2. User creation (cached - never changes)  
RUN groupadd -r mvidarr && useradd...

# 3. Python packages (cached if requirements unchanged)
COPY --from=builder /opt/python /usr/local

# 4. Application code (invalidated most frequently)
COPY --chown=mvidarr:mvidarr src/ /app/src/
```

#### Build Time Improvements
- **Selective dependencies**: Only essential build tools installed
- **Extended timeout**: `--timeout=1000` prevents network timeout failures
- **No-cache pip**: Prevents cache corruption issues
- **Parallel operations**: BuildKit enables parallel layer builds

## CI/CD Pipeline Build Process

### GitHub Actions Workflow

The build process is automated through `.github/workflows/ci-cd.yml`:

#### Build Triggers
- Push to `dev` branch
- Pull requests to `dev` 
- Push to `main` branch (production release)
- Manual workflow dispatch

#### Build Steps

1. **Code Quality Validation**
   ```yaml
   - name: Format and Lint Check
     run: |
       black --check src/
       isort --profile black --check-only src/
   ```

2. **Docker Build and Test**
   ```yaml
   - name: Build Docker Image
     uses: docker/build-push-action@v6
     with:
       file: Dockerfile.production
       tags: mvidarr:test
       cache-from: type=gha
       cache-to: type=gha,mode=max
   ```

3. **Security Scanning**: covered separately by `.github/workflows/security-scan.yml` (pip-audit, Bandit, Semgrep, Trivy — see `CLAUDE.md` § Security Implementation), not inline in the build workflow

4. **Registry Push** (if tests pass)
   ```yaml
   - name: Push to Registry
     uses: docker/build-push-action@v7
     with:
       push: true
       tags: |
         ghcr.io/prefect421/mvidarr:latest
         ghcr.io/prefect421/mvidarr:${{ github.sha }}
   ```

### Build Matrix
The test job runs against both supported Python versions:

```yaml
strategy:
  matrix:
    python-version: [3.11, 3.12]
```

The Docker image build itself targets `linux/amd64` only in CI (the Dockerfile has arm64-aware logic for manual `buildx` builds, but the automated pipeline doesn't build/test that platform).

## Version Management in Builds

### Version Metadata Update
Before significant builds, update version metadata:

```bash
# Get current commit and timestamp
CURRENT_COMMIT=$(git rev-parse --short HEAD)
CURRENT_TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%S.%6N")

# Update version.json
cat > version.json << EOF
{
  "version": "0.9.2",
  "build_date": "$CURRENT_TIMESTAMP", 
  "git_commit": "$CURRENT_COMMIT",
  "git_branch": "dev",
  "release_name": "Current Development"
}
EOF
```

### Automated Version Script
```bash
# Use the automated version update script
./scripts/update_version.sh

# Commit version changes
git add version.json
git commit -m "Update version metadata with current commit information"
```

## Build Performance Monitoring

### Build Time Tracking
```bash
# Time local builds
time docker build -f Dockerfile.production -t mvidarr:latest .

# Monitor CI build times
gh run list --workflow=ci-cd.yml --limit 10
```

### Image Size Monitoring
```bash
# Check current image size
docker images mvidarr:latest

# Use monitoring script
./scripts/docker-size-monitor.sh ghcr.io/prefect421/mvidarr latest

# Layer analysis
docker history mvidarr:latest
```

### Build Cache Analysis
```bash
# Check cache usage
docker system df

# Prune old cache
docker builder prune

# BuildKit cache inspection  
docker buildx du
```

## Build Troubleshooting

### Common Build Issues

#### 1. Package Installation Timeouts
**Symptom**: `ReadTimeoutError` during pip install
**Solution**: Extended timeout already configured in Dockerfile
```dockerfile
RUN pip install --no-cache-dir --timeout=1000 -r requirements.txt && \
    pip install --no-cache-dir --timeout=1000 -r requirements-fastapi.txt
```

#### 2. Memory Issues During Build
**Symptom**: Build process killed due to memory
**Solution**: 
- Increase Docker desktop memory allocation (4GB minimum)
- Use multi-stage build (already implemented)
- Clean build cache: `docker builder prune`

#### 3. MySQL Client Build Failures
**Symptom**: `mysql_config not found`
**Solution**: Build dependencies properly installed
```dockerfile
RUN apt-get install -y default-libmysqlclient-dev
```

#### 4. Permission Errors
**Symptom**: Permission denied in container
**Solution**: Consistent ownership in Dockerfile
```dockerfile
COPY --chown=mvidarr:mvidarr src/ /app/src/
```

#### 5. Context Size Too Large
**Symptom**: Docker build context exceeds limits
**Solution**: Proper `.dockerignore` configuration (implemented)
```dockerignore
data/musicvideos/
data/downloads/ 
data/thumbnails/
*.pyc
__pycache__/
```

### Build Environment Requirements

#### Development Environment
- Docker Engine 20.10+
- 4GB available RAM
- 10GB available disk space
- Python 3.12+ (for local development)
- Git (for version metadata)

#### CI/CD Environment  
- GitHub Actions runner (ubuntu-latest)
- Docker BuildKit enabled
- Registry authentication configured
- Secrets management for sensitive values

### Build Validation

#### Pre-Build Checklist
- [ ] Code formatted with Black 24.3.0
- [ ] Imports sorted with isort --profile black
- [ ] No linting errors
- [ ] Tests passing locally
- [ ] Version metadata updated
- [ ] Docker daemon running
- [ ] Build context under reasonable size limit

#### Post-Build Validation
- [ ] Image builds successfully
- [ ] Container starts without errors
- [ ] Application accessible on port 5000
- [ ] Database connection working
- [ ] Core functionality operational
- [ ] Security scan passes
- [ ] Image size within acceptable limits

## Build Optimization Guidelines

### Development Builds
1. **Use BuildKit**: Enable for parallel operations and better caching
2. **Mount cache**: Use volume mounts for package caches during development
3. **Layer awareness**: Understand which changes invalidate which layers
4. **Regular cleanup**: Remove unused images and containers

### Production Builds  
1. **Multi-stage**: Always use multi-stage for production
2. **Security scanning**: Include security validation in build process
3. **Size monitoring**: Track image size growth over time
4. **Cache strategy**: Implement proper cache-from/cache-to configuration
5. **Reproducible builds**: Pin all dependency versions

### CI/CD Pipeline
1. **Parallel jobs**: Run tests and builds in parallel where possible
2. **Cache optimization**: Use GitHub Actions cache effectively
3. **Build matrix**: Test multiple configurations
4. **Failure handling**: Implement proper error reporting and rollback
5. **Deployment automation**: Automate promotion to production registries

## Related Documentation

- [Dockerfile.production](https://github.com/prefect421/mvidarr/blob/main/Dockerfile.production) - Current multi-stage production build
- [Deployment Guide](DEPLOYMENT.md) - Production deployment procedures
- [Security Implementation](SECURITY_IMPLEMENTATION.md) - Security considerations in builds
- [Performance Monitoring](PERFORMANCE_MONITORING.md) - Build performance tracking

## Contributing to Build Process

When modifying the build process:

1. **Test locally first**: Validate changes in local environment
2. **Document changes**: Update this guide with modifications
3. **Monitor impact**: Track build time and image size effects
4. **Backward compatibility**: Ensure existing deployments continue working
5. **Security review**: Consider security implications of changes

---

**Note**: This build process documentation is kept current with the latest optimizations. Refer to git history for evolution of build improvements and lessons learned.