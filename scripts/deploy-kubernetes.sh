#!/bin/bash
# MVidarr Kubernetes Deployment Script
# Phase 3 Week 38: Container Orchestration & Kubernetes

set -euo pipefail

# Default values
ENVIRONMENT="development"
NAMESPACE=""
HELM_RELEASE_NAME=""
DRY_RUN=false
UPGRADE=false
SKIP_BUILD=false
LOCAL_REGISTRY=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
    exit 1
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

usage() {
    cat << EOF
MVidarr Kubernetes Deployment Script

Usage: $0 [OPTIONS]

Options:
    -e, --environment ENV    Target environment (development|staging|production) [default: development]
    -n, --namespace NS       Kubernetes namespace [default: mvidarr-ENV]
    -r, --release-name NAME  Helm release name [default: mvidarr-ENV]
    -d, --dry-run           Perform a dry-run deployment
    -u, --upgrade           Upgrade existing deployment
    -s, --skip-build        Skip Docker image build
    -l, --local-registry    Use local Docker registry
    -h, --help              Show this help message

Examples:
    $0 -e development                    # Deploy to development
    $0 -e staging -u                     # Upgrade staging deployment
    $0 -e production -d                  # Dry-run production deployment
    $0 -e development -l                 # Deploy to dev with local images
    
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -r|--release-name)
            HELM_RELEASE_NAME="$2"
            shift 2
            ;;
        -d|--dry-run)
            DRY_RUN=true
            shift
            ;;
        -u|--upgrade)
            UPGRADE=true
            shift
            ;;
        -s|--skip-build)
            SKIP_BUILD=true
            shift
            ;;
        -l|--local-registry)
            LOCAL_REGISTRY=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# Set defaults based on environment
if [[ -z "$NAMESPACE" ]]; then
    NAMESPACE="mvidarr-${ENVIRONMENT}"
fi

if [[ -z "$HELM_RELEASE_NAME" ]]; then
    HELM_RELEASE_NAME="mvidarr-${ENVIRONMENT}"
fi

# Validate environment
case $ENVIRONMENT in
    development|staging|production)
        ;;
    *)
        error "Invalid environment: $ENVIRONMENT. Must be one of: development, staging, production"
        ;;
esac

# Check required tools
check_prerequisites() {
    log "Checking prerequisites..."
    
    local missing_tools=()
    
    if ! command -v kubectl &> /dev/null; then
        missing_tools+=("kubectl")
    fi
    
    if ! command -v helm &> /dev/null; then
        missing_tools+=("helm")
    fi
    
    if ! command -v docker &> /dev/null && [[ "$SKIP_BUILD" != true ]]; then
        missing_tools+=("docker")
    fi
    
    if [[ ${#missing_tools[@]} -ne 0 ]]; then
        error "Missing required tools: ${missing_tools[*]}"
    fi
    
    # Check kubectl connectivity
    if ! kubectl cluster-info &> /dev/null; then
        error "Cannot connect to Kubernetes cluster. Please check your kubeconfig."
    fi
    
    info "Prerequisites check passed"
}

# Build Docker image
build_image() {
    if [[ "$SKIP_BUILD" == true ]]; then
        info "Skipping Docker image build"
        return
    fi
    
    log "Building Docker image..."
    
    local image_tag
    if [[ "$LOCAL_REGISTRY" == true ]]; then
        image_tag="mvidarr/api:${ENVIRONMENT}-$(git rev-parse --short HEAD)"
    else
        image_tag="ghcr.io/prefect421/mvidarr:${ENVIRONMENT}-$(git rev-parse --short HEAD)"
    fi
    
    docker build -t "$image_tag" .
    
    if [[ "$LOCAL_REGISTRY" != true ]]; then
        info "Pushing image to registry..."
        docker push "$image_tag"
    fi
    
    export IMAGE_TAG="$image_tag"
    info "Built and tagged image: $image_tag"
}

# Validate Kubernetes manifests
validate_manifests() {
    log "Validating Kubernetes manifests..."
    
    # Run our validation script
    if [[ -f "test_kubernetes_deployment.py" ]]; then
        python3 test_kubernetes_deployment.py
    else
        warn "Validation script not found, skipping manifest validation"
    fi
    
    # Validate Helm chart
    info "Validating Helm chart..."
    helm lint kubernetes/helm/mvidarr
    
    # Validate with kubeval if available
    if command -v kubeval &> /dev/null; then
        info "Running kubeval validation..."
        find kubernetes/manifests -name "*.yaml" -exec kubeval {} \;
    fi
}

# Create namespace if it doesn't exist
create_namespace() {
    log "Creating namespace: $NAMESPACE"
    
    if kubectl get namespace "$NAMESPACE" &> /dev/null; then
        info "Namespace $NAMESPACE already exists"
    else
        kubectl create namespace "$NAMESPACE"
        
        # Add labels to namespace
        kubectl label namespace "$NAMESPACE" \
            app.kubernetes.io/name=mvidarr \
            app.kubernetes.io/environment="$ENVIRONMENT" \
            app.kubernetes.io/managed-by=helm
    fi
}

# Install or upgrade Istio (if not already installed)
setup_istio() {
    if [[ "$ENVIRONMENT" != "production" ]]; then
        info "Skipping Istio setup for $ENVIRONMENT environment"
        return
    fi
    
    log "Setting up Istio service mesh..."
    
    # Check if Istio is installed
    if ! kubectl get namespace istio-system &> /dev/null; then
        warn "Istio not found. Please install Istio manually:"
        warn "  curl -L https://istio.io/downloadIstio | sh -"
        warn "  istioctl install --set values.defaultRevision=default"
        return
    fi
    
    # Enable Istio sidecar injection for our namespace
    kubectl label namespace "$NAMESPACE" istio-injection=enabled --overwrite
    
    # Apply Istio configurations
    info "Applying Istio configurations..."
    kubectl apply -f kubernetes/istio/ -n "$NAMESPACE"
}

# Deploy with Helm
helm_deploy() {
    log "Deploying with Helm..."
    
    local helm_cmd="helm"
    local action="install"
    
    if [[ "$UPGRADE" == true ]] || kubectl get secret -n "$NAMESPACE" "sh.helm.release.v1.${HELM_RELEASE_NAME}.v1" &> /dev/null; then
        action="upgrade"
    fi
    
    if [[ "$DRY_RUN" == true ]]; then
        helm_cmd="$helm_cmd --dry-run"
    fi
    
    local values_file="kubernetes/helm/mvidarr/values-${ENVIRONMENT}.yaml"
    if [[ ! -f "$values_file" ]]; then
        warn "Environment-specific values file not found: $values_file"
        values_file=""
    fi
    
    local helm_args=(
        "$action" "$HELM_RELEASE_NAME" kubernetes/helm/mvidarr
        --namespace "$NAMESPACE"
        --create-namespace
        --values kubernetes/helm/mvidarr/values.yaml
    )
    
    if [[ -n "$values_file" ]]; then
        helm_args+=(--values "$values_file")
    fi
    
    # Set image tag if built
    if [[ -n "${IMAGE_TAG:-}" ]]; then
        helm_args+=(--set "image.tag=${IMAGE_TAG#*:}")
    fi
    
    # Environment-specific settings
    helm_args+=(
        --set "app.environment=$ENVIRONMENT"
        --set "global.environment=$ENVIRONMENT"
    )
    
    # Add wait and timeout for non-dry-run deployments
    if [[ "$DRY_RUN" != true ]]; then
        helm_args+=(--wait --timeout=10m)
    fi
    
    info "Running: $helm_cmd ${helm_args[*]}"
    $helm_cmd "${helm_args[@]}"
}

# Verify deployment
verify_deployment() {
    if [[ "$DRY_RUN" == true ]]; then
        info "Skipping deployment verification (dry-run mode)"
        return
    fi
    
    log "Verifying deployment..."
    
    # Check pod status
    info "Checking pod status..."
    kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=mvidarr"
    
    # Wait for rollout to complete
    info "Waiting for deployment rollout..."
    kubectl rollout status deployment/"$HELM_RELEASE_NAME" -n "$NAMESPACE" --timeout=300s
    
    # Check service endpoints
    info "Checking service endpoints..."
    kubectl get svc -n "$NAMESPACE"
    
    # Test health endpoint if possible
    info "Testing health endpoint..."
    local pod_name
    pod_name=$(kubectl get pods -n "$NAMESPACE" -l "app.kubernetes.io/name=mvidarr" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")
    
    if [[ -n "$pod_name" ]]; then
        if kubectl exec -n "$NAMESPACE" "$pod_name" -- curl -f http://localhost:5000/health &> /dev/null; then
            info "Health check passed"
        else
            warn "Health check failed or not available"
        fi
    fi
}

# Post-deployment tasks
post_deployment() {
    if [[ "$DRY_RUN" == true ]]; then
        return
    fi
    
    log "Running post-deployment tasks..."
    
    # Show deployment information
    info "Deployment Information:"
    echo "  Environment: $ENVIRONMENT"
    echo "  Namespace: $NAMESPACE"
    echo "  Release Name: $HELM_RELEASE_NAME"
    echo "  Image Tag: ${IMAGE_TAG:-default}"
    
    # Show access information
    info "Access Information:"
    case $ENVIRONMENT in
        development)
            echo "  URL: https://dev.mvidarr.example.com"
            ;;
        staging)
            echo "  URL: https://staging.mvidarr.example.com"
            ;;
        production)
            echo "  URL: https://mvidarr.example.com"
            echo "  API: https://api.mvidarr.example.com"
            ;;
    esac
    
    # Show useful kubectl commands
    info "Useful commands:"
    echo "  View pods: kubectl get pods -n $NAMESPACE"
    echo "  View logs: kubectl logs -n $NAMESPACE -l app.kubernetes.io/name=mvidarr"
    echo "  Port forward: kubectl port-forward -n $NAMESPACE svc/$HELM_RELEASE_NAME 8080:80"
    echo "  Helm status: helm status $HELM_RELEASE_NAME -n $NAMESPACE"
}

# Main execution
main() {
    log "Starting MVidarr Kubernetes deployment"
    log "Environment: $ENVIRONMENT"
    log "Namespace: $NAMESPACE"
    log "Release Name: $HELM_RELEASE_NAME"
    
    if [[ "$DRY_RUN" == true ]]; then
        info "DRY RUN MODE - No changes will be made"
    fi
    
    check_prerequisites
    validate_manifests
    build_image
    create_namespace
    setup_istio
    helm_deploy
    verify_deployment
    post_deployment
    
    log "Deployment completed successfully!"
}

# Run main function
main "$@"