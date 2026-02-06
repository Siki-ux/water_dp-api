#!/bin/bash

# Ensure TSM Orchestration is running (Optional check, but helpful)
# We assume the user knows to run ./up.sh in tsm-orchestration first.

echo "Starting Water DP API in TSM Mode..."
echo "This will rebuild images and connect services to the TSM network."

# Run docker compose with both files
# Pass arguments to rebuild only specific services (e.g. ./run_with_tsm.sh api worker)
# If no arguments provided, it builds everything defined in the compose files.

BUILD_FLAG=""
SERVICES=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -b|--build)
            BUILD_FLAG="--build"
            shift
            ;;
        *)
            SERVICES="$SERVICES $1"
            shift
            ;;
    esac
done

if [ -z "$SERVICES" ]; then
    echo "Starting ALL services (use -b to force rebuild)..."
    docker compose -f docker-compose.yml -f docker-compose.tsm.yml up $BUILD_FLAG -d
else
    echo "Starting services:$SERVICES (use -b to force rebuild)"
    docker compose -f docker-compose.yml -f docker-compose.tsm.yml up $BUILD_FLAG -d $SERVICES
fi

echo ""
echo "Services started."
echo "App UI: http://localhost:3000"
echo "API Docs: http://localhost:8000/docs"
