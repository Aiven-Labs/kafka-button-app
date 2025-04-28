#!/usr/bin/env bash

set -Eeuo pipefail

args=("$@")

# Let's start with a more-or-less literal record of what *I* type.
# Assumes that `avn user login` has been done
#
# This script is not trying to use the optimal, takes least time to run, route
# - instead it's acting through a "story" of what we're doing. That means we
# WILL end up waiting for services to start when we maybe don't need to if we
# changed the order of things
#
# BEWARE that this script changes the default project

# See
# * https://www.gnu.org/software/bash/manual/html_node/Bourne-Shell-Builtins.html
#   for the `:` operator
# * https://www.gnu.org/software/bash/manual/html_node/Shell-Parameter-Expansion.html
#   for the `${thing1:=thing2}` expansion

BASE_SERVICE_NAME=kafka-button-app
DEFAULT_PROJECT_NAME=tibs-devrel
DEFAULT_TOPIC_NAME=button_presses

ENV_FILE=create_services.env

usage()
{
    echo "Usage: $(basename $0) [-h] [-n BASE_SERVICE_NAME] [-p PROJECT_NAME] [-t TOPIC_NAME]"
}

help()
{
    usage
    echo
    echo "Create all the services for the Kafka Button App workshop"
    echo
    echo "  -n BASE_SERVICE_NAME    The preferred start for service names."
    echo "                          The default is $BASE_SERVICE_NAME"
    echo "  -p PROJECT_NAME         The project name. Defaults to the value"
    echo "                          of \$PROJECT_NAME, or (if that's not set)"
    echo "                          to $DEFAULT_PROJECT_NAME"
    echo "  -t TOPIC_NAME           The Kafka topic name. Defaults to the value"
    echo "                          of \$KAFKA_BUTTON_TOPIC, or (if that's not set)"
    echo "                          to $DEFAULT_TOPIC_NAME"
    echo
    echo "New services will be called \$BASE_SERVICE_NAME-kafka, -pg, -ch."
    echo
    echo "Beware that this script switches to the chosen Aiven project, and that"
    echo "choice will persist into the caller's environment."
    echo
    echo "At the end, a variety of environment values are written to the file"
    echo "$ENV_FILE"
}

# Note: the `:` at the start of `:hn:` means "do silent processing" which
# leaves error reporting up to us, and enables the `:)` case
while getopts ":hn:p:t:" flag
do
    case $flag in
        h)
            help
            exit;;
        n)
            BASE_SERVICE_NAME=$OPTARG;;
        p)
            PROJECT_NAME=$OPTARG;;
        t)
            TOPIC_NAME=$OPTARG;;
        :)
            echo "Option -${OPTARG} needs an argument"
            usage
            exit 1;;
        ?)
            echo "Invalid option -$OPTARG"
            echo
            usage
            exit 1;;
    esac
done

# "Forget" the arguments we've consumed
shift $((OPTIND - 1))

if [ $# -gt 0 ]
then
    echo "Unexpected $1"
    echo
    usage
    exit 1
fi

: ${PROJECT_NAME:=$DEFAULT_TOPIC_NAME}
: ${TOPIC_NAME:=$DEFAULT_TOPIC_NAME}

KAFKA_SERVICE_NAME=$BASE_SERVICE_NAME-kafka
PG_SERVICE_NAME=$BASE_SERVICE_NAME-pg
CH_SERVICE_NAME=$BASE_SERVICE_NAME-ch

echo "Base service name is $BASE_SERVICE_NAME"
echo "Project is $PROJECT_NAME"
echo "Topic name is $TOPIC_NAME"

# It's a bit early to create the temporary directory, but let's do it
# now while we're doing other setup
temp_dir=$(mktemp -d "${TMPDIR:-/tmp}$(basename $0).XXXX")

echo "Switch to project $PROJECT_NAME"
avn project switch $PROJECT_NAME

# TODO Should paramerise cloud and plan
# TODO Should probably *not* allow topic auto creation
echo "Create Kafka service $KAFKA_SERVICE_NAME"
avn service create $KAFKA_SERVICE_NAME          \
        --service-type kafka                    \
        --cloud google-europe-west1             \
        --plan business-4                       \
        -c kafka_connect=true                   \
        -c schema_registry=true                 \
        -c kafka.auto_create_topics_enable=true

# We'll need the service URI later on
KAFKA_SERVICE_URI=$(avn service get $KAFKA_SERVICE_NAME --format '{service_uri}')

echo "Wait for the Kafka service to start"
avn service wait $KAFKA_SERVICE_NAME

echo "Download the Kafka certification files"
# (it will create the directory if necessary)
avn service user-creds-download $KAFKA_SERVICE_NAME --username avnadmin -d certs

# We know we're going to want to use tiered storage, so we need to enable
# it for this service
echo "Enable tiered storage"
avn service update                  \
   $KAFKA_SERVICE_NAME              \
   -c tiered_storage.enabled=true

# Wait until it is enabled
echo "Wait for tiered storage to be enabled"
echo "Is it enabled alredy? $(avn service get kafka-button-app-kafka --json | jq -r '.user_config.tiered_storage.enabled')"
while [ "$(avn service get kafka-button-app-kafka --json | jq -r '.user_config.tiered_storage.enabled')" != "true" ]
do
    echo "Waiting for tiered storage to be enabled"
done

# Somehow, that's not enough - I still get
#   "Cannot enable remote storage when service does not have tiered storage enabled"
# so let's add a pause as well
echo "Pause for safety (?)"
sleep 5

# TODO parameterise the various numeric arguments
# Note that these values are deliberately chosen to be low for demonstration purposes
# - we want to illustrate tiered storage being used!
echo "Create topic $TOPIC_NAME"
avn service topic-create    \
   --partitions 3            \
   --replication 2           \
   --remote-storage-enable   \
   --local-retention-ms 500 \
   --local-retention-bytes 500 \
   $KAFKA_SERVICE_NAME $TOPIC_NAME

# TODO parameterise the cloud and plan
echo "Create PostgreSQL service $PG_SERVICE_NAME"
avn service create $PG_SERVICE_NAME        \
   --service-type pg                       \
   --cloud google-europe-west1             \
   --plan hobbyist

echo "Wait for the PostgreSQL service to start"
avn service wait $PG_SERVICE_NAME

PG_SERVICE_URI=$(avn service connection-info pg uri $PG_SERVICE_NAME)

echo "Create the PostgreSQL table"
psql "$PG_SERVICE_URI" <<EOF
CREATE TYPE action as ENUM ('EnterPage', 'PressButton');
CREATE TABLE button_presses (
    "id" bigint generated always as identity primary key,
    "session_id" uuid not null,
    "timestamp" bigint,
    "cohort" smallint,
    "action" text not null,
    "country_name" text not null,
    "country_code" char(2) not null,
    "subdivision_name" text,
    "subdivision_code" text,
    "city_name" text
);
EOF

echo "Get Karapace schema registry URI"
SCHEMA_REGISTRY_URI=$(avn service get $KAFKA_SERVICE_NAME --json | jq -r '.connection_info.schema_registry_uri')

echo "Get PostgreSQL connection details"
# We could probably do this more efficiently by writing to a JSON file and
# then reading the invividual values from there, but this is OK for now
PG_HOST=$(avn service get $PG_SERVICE_NAME --json | jq -r .service_uri_params.host)
PG_PORT=$(avn service get $PG_SERVICE_NAME --json | jq -r .service_uri_params.port)
PG_DBNAME=$(avn service get $PG_SERVICE_NAME --json | jq -r .service_uri_params.dbname)
PG_SSLMODE=$(avn service get $PG_SERVICE_NAME --json | jq -r .service_uri_params.sslmode)
PG_USERNAME=$(avn service get $PG_SERVICE_NAME --json | jq -r .service_uri_params.username)
PG_PASSWORD=$(avn service get $PG_SERVICE_NAME --json | jq -r .service_uri_params.password)

echo "Get Karapace (Kafka schema registry) connection details"
SCHEMA_REGISTRY_HOST=$(avn service get $KAFKA_SERVICE_NAME --json | jq -r '.components | map(select(.component == "schema_registry"))[0].host')
SCHEMA_REGISTRY_PORT=$(avn service get $KAFKA_SERVICE_NAME --json | jq -r '.components | map(select(.component == "schema_registry"))[0].port')
SCHEMA_REGISTRY_USERNAME=$(avn service get $KAFKA_SERVICE_NAME --json | jq -r .users[0].username)
SCHEMA_REGISTRY_PASSWORD=$(avn service get $KAFKA_SERVICE_NAME --json | jq -r .users[0].password)


echo "Create pg_avro_sink.json file (in temporary directory)"
avro_sink_json_file=$temp_dir/pg_avro_sink.json
cat <<EOF > $avro_sink_json_file
{
    "name":"sink_button_presses_avro_karapace",
    "connector.class": "io.aiven.connect.jdbc.JdbcSinkConnector",
    "topics": "button_presses",
    "connection.url": "jdbc:postgresql://$PG_HOST:$PG_PORT/$PG_DBNAME?sslmode=$PG_SSLMODE",
    "connection.user": "$PG_USERNAME",
    "connection.password": "$PG_PASSWORD",
    "tasks.max":"1",
    "auto.create": "false",
    "auto.evolve": "false",
    "insert.mode": "insert",
    "delete.enabled": "false",
    "pk.mode": "none",
    "key.converter": "io.confluent.connect.avro.AvroConverter",
    "key.converter.schema.registry.url": "https://$SCHEMA_REGISTRY_HOST:$SCHEMA_REGISTRY_PORT",
    "key.converter.basic.auth.credentials.source": "USER_INFO",
    "key.converter.schema.registry.basic.auth.user.info": "$SCHEMA_REGISTRY_USERNAME:$SCHEMA_REGISTRY_PASSWORD",
    "value.converter": "io.confluent.connect.avro.AvroConverter",
    "value.converter.schema.registry.url": "https://$SCHEMA_REGISTRY_HOST:$SCHEMA_REGISTRY_PORT",
    "value.converter.basic.auth.credentials.source": "USER_INFO",
    "value.converter.schema.registry.basic.auth.user.info": "$SCHEMA_REGISTRY_USERNAME:$SCHEMA_REGISTRY_PASSWORD"
}
EOF

echo "Create the PG Avro Sink connector"
avn service connector create $KAFKA_SERVICE_NAME @${avro_sink_json_file}

# Once that has started up, any messages from Kafka should end up in PosgreSQL


# TODO parameterise the cloud and plan
echo "Creating ClickHouse service $CH_SERVICE_NAME"
avn service create $CH_SERVICE_NAME          \
        --service-type clickhouse            \
        --cloud google-europe-west1          \
        --plan startup-16


echo "Wait for the ClickHouse service to start"
avn service wait $CH_SERVICE_NAME

echo "Create the Kafka -> ClickHouse service integration"
avn service integration-create            \
    --integration-type clickhouse_kafka   \
    --source-service $KAFKA_SERVICE_NAME\
    --dest-service $CH_SERVICE_NAME

# TODO I hope there's a better way to do this :)
echo "Pause to let that happen..."
sleep 5

echo "Get the Kafka -> ClickHouse service integration ID"
KAFKA_CH_SERVICE_INTEGRATION_ID=$(avn service integration-list $CH_SERVICE_NAME --json | jq -r '. | map(select(.integration_type == "clickhouse_kafka"))[0].service_integration_id')

echo "Create kafka_ch_integration_config.json file (in temporary directory)"
kafka_ch_integration_config_file=$temp_dir/kafka_ch_integration_config.json
cat <<EOF > $kafka_ch_integration_config_file
{
    "tables": [
        {
            "name": "${TOPIC_NAME}_from_kafka",
            "columns": [
                {"name": "session_id", "type": "UUID"},
                {"name": "timestamp", "type": "DateTime64(6)"},
                {"name": "action", "type": "String"},
                {"name": "country_name", "type": "String"},
                {"name": "country_code", "type": "FixedString(2)"},
                {"name": "subdivision_name", "type": "String"},
                {"name": "subdivision_code", "type": "String"},
                {"name": "city_name", "type": "String"},
                {"name": "cohort", "type": "Nullable(Smallint)"}
            ],
            "topics": [{"name": "$TOPIC_NAME"}],
            "data_format": "AvroConfluent",
            "group_name": "button_presses_from_kafka_consumer"
        }
    ]
}
EOF

echo "Update the Kafka -> ClickHouse service integration with topic and schema data"
avn service integration-update \
    $KAFKA_CH_SERVICE_INTEGRATION_ID \
    --user-config-json @$kafka_ch_integration_config_file

# TODO I hope there's a better way to do this :)
echo "Pause to let that happen..."
sleep 5

echo "Get the ClickHouse connection details"
CH_USER=$(avn service get $CH_SERVICE_NAME --json | jq -r .service_uri_params.user)
CH_PASSWORD=$(avn service get $CH_SERVICE_NAME --json | jq -r .service_uri_params.password)
CH_HOST=$(avn service get $CH_SERVICE_NAME --json | jq -r .service_uri_params.host)
CH_PORT=$(avn service get $CH_SERVICE_NAME --json | jq -r .service_uri_params.port)

# Do the following in two actions to see if that gives time for the table
# to "take" before doing the subsequent command

echo "Create the ClickHouse target table"

clickhouse_create_button_presses=$temp_dir/clickhouse_create_button_presses.sql
cat <<EOF > ${clickhouse_create_button_presses}
CREATE TABLE button_presses (
    session_id UUID,
    timestamp DateTime('UTC'),
    action String,
    country_name String,
    country_code FixedString(2),
    subdivision_name String,
    subdivision_code String,
    city_name String,
    cohort Nullable(Smallint)
)
ENGINE = ReplicatedMergeTree
ORDER BY timestamp;
EOF

echo "SQL created:"
cat $clickhouse_create_button_presses
echo "End of SQL"

clickhouse client \
    --host $CH_HOST --port $CH_PORT \
    --user $CH_USER --password $CH_PASSWORD \
    --secure \
    --queries-file $clickhouse_create_button_presses

echo "Create the ClickHouse materialized view"

clickhouse_create_materialized_view=$temp_dir/clickhouse_create_materialized_view.sql
cat <<EOF > ${clickhouse_create_materialized_view}
CREATE MATERIALIZED VIEW materialised_view TO button_presses AS
SELECT * FROM \`service_${KAFKA_SERVICE_NAME}\`.${TOPIC_NAME}_from_kafka;
EOF

echo "SQL created:"
cat $clickhouse_create_materialized_view
echo "End of SQL"

clickhouse client \
    --host $CH_HOST --port $CH_PORT \
    --user $CH_USER --password $CH_PASSWORD \
    --secure \
    --queries-file $clickhouse_create_materialized_view

# Leave behind a record of all the useful environment variables
# Note that this overwrites any previous value *unless* the Bash
# set builtin `noclobber` has been set, in which case it will
# fail if the file exists
echo "Write environment values to $ENV_FILE"
cat <<EOF > $ENV_FILE
# High level values
PROJECT_NAME=$PROJECT_NAME
KAFKA_SERVICE_NAME=$KAFKA_SERVICE_NAME
KAFKA_BUTTON_TOPIC=$TOPIC_NAME
PG_SERVICE_NAME=$PG_SERVICE_NAME
CH_SERVICE_NAME=$CH_SERVICE_NAME
# Specific connection details
KAFKA_SERVICE_URI=$KAFKA_SERVICE_URI
SCHEMA_REGISTRY_URI=$SCHEMA_REGISTRY_URI
PG_SERVICE_URI=$PG_SERVICE_URI
CH_USER=$CH_USER
CH_PASSWORD=$CH_PASSWORD
CH_HOST=$CH_HOST
CH_PORT=$CH_PORT
# ClickHouse client connection command:
#  clickhouse client --host $CH_HOST --port $CH_PORT --user $CH_USER --password $CH_PASSWORD --secure
EOF
