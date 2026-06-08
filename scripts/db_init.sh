#!/bin/bash
set -e

echo "--- SomaAI Infrastructure Initialization ---"

# 1. Wait for Postgres to be ready
echo "Waiting for PostgreSQL at ${SOMAAI_DATABASE_URL}..."
# Extract host and port from URL
DB_URL=$SOMAAI_DATABASE_URL
# Strip postgresql+asyncpg://
STRIPPED=${DB_URL#*@}
DB_HOST_PORT=${STRIPPED%/*}
DB_HOST=${DB_HOST_PORT%:*}
DB_PORT=${DB_HOST_PORT#*:}
if [ "$DB_HOST" == "$DB_HOST_PORT" ]; then DB_PORT=5432; fi

until curl -s http://$DB_HOST:$DB_PORT > /dev/null 2>&1 || [ $? -eq 52 ]; do
  # pg_isready is better if available, but let's just attempt a connection
  echo "Database is unavailable - sleeping"
  sleep 1
done

echo "Database is up!"

# 2. Run Migrations
echo "Running Alembic migrations..."
alembic upgrade head
echo "Migrations completed."

# 3. Seed Metadata
echo "Seeding metadata..."
python -m scripts.seed_meta
echo "Seeding completed."

echo "--- Infrastructure Setup Success ---"
exit 0
