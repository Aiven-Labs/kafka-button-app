#!/usr/bin/env sh

# Create PG and CH tables
./setup_scripts/create_pg_table.sh
./setup_scripts/create_clickhouse_tables.sh

# Download Kafka certs from avn client
# AIVEN_TOKEN env variable needs to be assigned
# TODO: Check if there is a default ENVIRONMENT VARIABLE THAT WORKS WITH AVN CLI
# Kafka certificates
# Existing certs will be overwritten

avn --auth-token "$AIVEN_TOKEN" service user-creds-download \
  --project $PROJECT_NAME \
  $KAFKA_SERVICE_NAME --username avnadmin -d ./certs

# run the application
fastapi run src/app.py --port 3000
