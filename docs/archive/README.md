# Documentation Archive

This directory contains archived documentation files that have been superseded by updated versions or are no longer applicable to current MVidarr deployments.

## Archived Files

### DEPLOYMENT_GUIDE-OLD.md
**Archived**: December 3, 2025
**Reason**: Contained outdated Docker Compose configurations and deployment strategies that no longer match the simplified 3-container architecture.

**Old Approach:**
- Multiple docker-compose variants (6+ files)
- Complex multi-container setups with separate Celery containers
- Outdated environment variable structure
- Docker Swarm and Kubernetes examples (overly complex for home use)

**Current Approach:**
- Single `docker-compose.yml` in root directory
- Simplified 3-container architecture (mvidarr, mariadb, redis)
- FastAPI + Celery managed by supervisord in single container
- Clear `.env` file configuration
- Focus on consumer-grade self-hosting

**Replacement**: See [docs/installation.md](../installation.md) for current deployment instructions.

## Why Files Are Archived

MVidarr v0.10.0-beta.1 introduced significant simplifications to the deployment process:

1. **Simplified Docker Architecture** - Reduced from 6+ containers to 3 containers
2. **Single Configuration File** - One docker-compose.yml instead of 5 variants
3. **Clear Environment Setup** - Single .env.example with inline documentation
4. **Consumer Focus** - Removed enterprise/cloud deployment complexity

These changes make MVidarr easier to deploy and maintain for home users, which is the primary target audience.

## Reference

If you need advanced deployment patterns (Kubernetes, Docker Swarm, cloud deployments), the archived guides contain historical reference information. However, these are not officially supported or tested with current versions.

For current deployment information:
- [Installation Guide](../installation.md) - Main installation documentation
- [README.md](../../README.md) - Quick start guide
- [.env.example](../../.env.example) - Configuration template
- [docker-compose.yml](../../docker-compose.yml) - Production deployment file

## Archive Policy

Documentation is archived when:
1. It references deprecated deployment methods
2. It conflicts with current best practices
3. It adds unnecessary complexity for the target audience
4. Maintained for historical reference only

**Last Updated**: December 3, 2025
