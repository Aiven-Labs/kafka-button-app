#!/usr/bin/env sh

# Set up the environment for our app, and then run it

## The example from https://github.com/Aiven-Labs/fake-data-producer-for-apache-kafka-docker
## reads the environment variables from a file. Otherwise, we might pass them in to the
## container *as* environment variables
##
## source /app/env.conf
##
## We expect the following environment variables to already be set
##
## AIVEN_TOKEN
## PROJECT_NAME
## KAFKA_SERVICE_NAME
## CH_SERVICE_NAME

# Kafka
#
# echo $KAFKA_SERVICE_NAME
# echo $CH_SERVICE_NAME
# echo $PROJECT_NAME

export KAFKA_SERVICE_URI=$(avn --auth-token "$AIVEN_TOKEN" service get \
  --project $PROJECT_NAME \
  $KAFKA_SERVICE_NAME --format '{service_uri}')

# Kafka certificates
rm -rf ./certs
avn --auth-token "$AIVEN_TOKEN" service user-creds-download \
  --project $PROJECT_NAME \
  $KAFKA_SERVICE_NAME --username avnadmin -d ./certs

# Schema registry
export SCHEMA_REGISTRY_URI=$(avn --auth-token "$AIVEN_TOKEN" service get \
  --project $PROJECT_NAME \
  $KAFKA_SERVICE_NAME --json | jq -r '.connection_info.schema_registry_uri')

# ClickHouse
export CH_HOST=$(avn --auth-token "$AIVEN_TOKEN" service get \
  --project $PROJECT_NAME \
  $CH_SERVICE_NAME --json | jq -r '.components | map(select(.component == "clickhouse_https"))[0].host')
export CH_PORT=$(avn --auth-token "$AIVEN_TOKEN" service get \
  --project $PROJECT_NAME \
  $CH_SERVICE_NAME --json | jq -r '.components | map(select(.component == "clickhouse_https"))[0].port')
export CH_USERNAME=$(avn --auth-token "$AIVEN_TOKEN" service get \
  --project $PROJECT_NAME \
  $CH_SERVICE_NAME --json | jq -r '.service_uri_params.user')
export CH_PASSWORD=$(avn --auth-token "$AIVEN_TOKEN" service get \
  --project $PROJECT_NAME \
  $CH_SERVICE_NAME --json | jq -r '.service_uri_params.password')

# And finally run the application
fastapi run src/app.py --port 3000
