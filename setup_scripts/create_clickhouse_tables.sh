echo "Creating Temporary Dir"
temp_dir=$(mktemp -d "${TMPDIR:-/tmp}$(basename $0).XXXX")

echo "Create the ClickHouse target table"

clickhouse_create_button_presses=$temp_dir/clickhouse_create_button_presses.sql
cat <<EOF >${clickhouse_create_button_presses}
CREATE TABLE ${TOPIC_NAME} (
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
