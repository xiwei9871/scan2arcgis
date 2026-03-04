#!/bin/bash
# Deployment script for Geological Map Digitizer

set -e

echo "======================================"
echo "Geological Map Digitizer - Deployment"
echo "======================================"

# Configuration
IMAGE_PREFIX="geological-map-digitizer"
BACKEND_IMAGE="${IMAGE_PREFIX}-backend"
FRONTEND_IMAGE="${IMAGE_PREFIX}-frontend"
REGISTRY=${REGISTRY:-"localhost:5000"}

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Docker is installed
check_docker() {
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        log_error "Docker Compose is not installed"
        exit 1
    fi

    log_info "Docker and Docker Compose are installed"
}

# Build Docker images
build_images() {
    log_info "Building Docker images..."

    # Build backend
    log_info "Building backend image..."
    docker build -t ${BACKEND_IMAGE}:latest ./backend

    # Build frontend
    log_info "Building frontend image..."
    docker build -t ${FRONTEND_IMAGE}:latest ./frontend

    log_info "Docker images built successfully"
}

# Stop existing containers
stop_containers() {
    log_info "Stopping existing containers..."
    docker-compose down
    log_info "Containers stopped"
}

# Start services
start_services() {
    log_info "Starting services..."
    docker-compose up -d
    log_info "Services started"
}

# Show status
show_status() {
    log_info "Container status:"
    docker-compose ps
}

# Run health checks
health_check() {
    log_info "Running health checks..."

    # Wait for services to be ready
    log_info "Waiting for services to start (30 seconds)..."
    sleep 30

    # Check backend health
    log_info "Checking backend health..."
    if curl -f http://localhost:8000/health &> /dev/null; then
        log_info "Backend is healthy"
    else
        log_error "Backend health check failed"
    fi

    # Check frontend
    log_info "Checking frontend..."
    if curl -f http://localhost:80/ &> /dev/null; then
        log_info "Frontend is accessible"
    else
        log_error "Frontend health check failed"
    fi
}

# Main deployment flow
main() {
    case "${1:-deploy}" in
        deploy)
            check_docker
            build_images
            stop_containers
            start_services
            show_status
            health_check
            log_info "Deployment complete!"
            log_info "Frontend: http://localhost:80"
            log_info "Backend API: http://localhost:8000"
            log_info "API Docs: http://localhost:8000/docs"
            ;;
        build)
            check_docker
            build_images
            ;;
        stop)
            stop_containers
            ;;
        restart)
            stop_containers
            start_services
            show_status
            ;;
        status)
            show_status
            ;;
        health)
            health_check
            ;;
        logs)
            docker-compose logs -f
            ;;
        clean)
            log_warn "Removing all containers and volumes..."
            docker-compose down -v
            log_info "Cleanup complete"
            ;;
        *)
            echo "Usage: $0 {deploy|build|stop|restart|status|health|logs|clean}"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
