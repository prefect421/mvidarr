# Documentation Archive

This directory contains archived documentation files that have been superseded by updated versions or are no longer applicable to current MVidarr deployments.

## Archived Files

### V1.0.0_TODO_MASTER_LIST.md, V1.0.0_DEVELOPMENT_START.md, to-do.md, issues/Issues.md, requirements/Features.md
**Archived**: August 9, 2026
**Reason**: A first v1.0.0 planning effort (dated 2025-11-10, targeting the Installation Wizard as the headline feature). Every issue it references (#163, #91-97, #159, #134-137, #161) is closed — the effort completed and the project reset to 0.x versioning afterward. `to-do.md` and `Issues.md`/`Features.md` are earlier point-in-time status snapshots (July 2025) from the same general era, since superseded by the live GitHub issue tracker.

**Current planning**: See the GitHub issue tracker and the `v1.0.0` milestone for the current v1.0.0 push (started 2026-08-09).

### 0.9.5-STRATEGIC_PIVOT.md, 0.9.6-QUALITY_ASSURANCE_PLAN.md, 0.9.8-COMPLETION.md
**Archived**: August 9, 2026
**Reason**: Version-specific planning/completion snapshots for releases from over a year of development ago. Historical record only.

### FASTAPI_MIGRATION_COMPLETE.md
**Archived**: August 9, 2026
**Reason**: Claims the Flask→FastAPI migration is 100% complete. It isn't — see [GitHub issue #313](https://github.com/prefect421/mvidarr/issues/313): 14 files still import Flask directly as of this date, some of it dead code, some still live in the auth path. Kept for historical context on what the migration intended to achieve, not as a statement of current fact.

### FINAL_PROJECT_STATUS.md, DOCUMENTATION_REVIEW_2025.md, DOCKER_COMPOSE_REVIEW_2025.md
**Archived**: August 9, 2026
**Reason**: Point-in-time project status and review snapshots, superseded by CLAUDE.md's maintained version history and this repo's live documentation.

### diagnostics/ (check_prod_job.sh, deploy_fix_to_production.sh, diagnose_indexing.py, fix_path_mismatch.py, monitor_indexing_job.sh, PRODUCTION_CRASHLOOP_FIX.md, PRODUCTION_INDEXING_FIX.md, verify_production.sh)
**Archived**: August 9, 2026
**Reason**: One-off scripts and notes written for specific past production incidents. Useful as historical reference for how those incidents were diagnosed and resolved, not living operational documentation.

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

**Last Updated**: August 9, 2026
