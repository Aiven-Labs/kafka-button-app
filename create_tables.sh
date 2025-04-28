echo "Creating Temporary"
temp_dir=$(mktemp -d "${TMPDIR:-/tmp}$(basename $0).XXXX")

echo "Create the PostgreSQL table"

PG_SERVICE_URI=$(avn service connection-info pg uri $PG_SERVICE_NAME)
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

echo "Create the ClickHouse target table"

clickhouse_create_button_presses=$temp_dir/clickhouse_create_button_presses.sql
cat <<EOF >${clickhouse_create_button_presses}
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
cat <<EOF >${clickhouse_create_materialized_view}
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
