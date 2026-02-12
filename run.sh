
# SomaAI Runner Script
#   Commands:
#     local   - Run the app locally (default)
#     docker  - Run with Docker Compose
#     build   - Build Docker image only

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

show_help() {
    echo "SomaAI Runner"
    echo ""
    echo "Usage: ./run.sh [command]"
    echo ""
    echo "Commands:"
    echo "  local    Run the app locally using uv (default)"
    echo "  docker   Run with Docker Compose"
    echo "  build    Build Docker image only"
    echo "  stop     Stop Docker containers"
    echo "  help     Show this help message"
}

run_local() {
    echo "Starting SomaAI locally..."
    
    if ! command -v uv &> /dev/null; then
        echo "Error: uv is not installed."
        echo "Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
    
    # Sync dependencies
    uv sync
    
    # Run the application
    uv run uvicorn somaai.main:app --reload --host 0.0.0.0 --port 8000
}

run_docker() {
    echo "Starting SomaAI with Docker..."
    
    if ! command -v docker &> /dev/null; then
        echo "Error: Docker is not installed."
        exit 1
    fi
    
    docker-compose -f docker/docker-compose.yml up --build
}

build_docker() {
    echo "Building SomaAI Docker image..."
    docker build -t somaai:latest -f docker/Dockerfile .
}

stop_docker() {
    echo "Stopping SomaAI Docker containers..."
    docker-compose -f docker/docker-compose.yml down
}

# Main
case "${1:-local}" in
    local)
        run_local
        ;;
    docker)
        run_docker
        ;;
    build)
        build_docker
        ;;
    stop)
        stop_docker
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        show_help
        exit 1
        ;;
esac
