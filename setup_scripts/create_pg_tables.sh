!#/usr/bin/env bash

echo "Create the PostgreSQL table"

psql "$PG_SERVICE_URI" <<EOF
CREATE TYPE action as ENUM ('EnterPage', 'PressButton');
CREATE TABLE $TOPIC_NAME (
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

psql "$PG_SERVICE_URI" -c "\d button_presses"
