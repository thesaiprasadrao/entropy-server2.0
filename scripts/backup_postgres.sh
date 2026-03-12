#!/bin/bash

# Create backups directory if it doesn't exist
mkdir -p backups/postgres

# Run pg_dump inside the postgres container
# Get credentials from .env or use defaults
docker exec entropy_postgres pg_dump -U ctf_user ctf_db > backups/postgres/backup_$(date +%F_%H-%M).sql

echo "Backup completed successfully."
