# Summary - getting things to run

> **Note** that I use `set -x` and other [fish shell](https://fishshell.com/)
> conventions in the following - this will be changed to Bash conventions in the
> final set of instructions. 

## General setup

```
; python -m venv venv
; source venv/bin/activate.fish    # why yes, I use the fish shell
; pip install -r requirements.txt
```

## Kafka setup

I'm going to do things with the `avn` command - it's easier to describe in a
document like this, and it faciliates copy-and-paste as a way of following along.

Since we're working with Python, we want a virtual environment

```
; python -m venv venv
; source venv/bin/activate.fish    # why yes, I use the fish shell
; pip install -r requirements.txt
```

Make sure I have `avn`, and upgrade it if necessary
```
; pip install -U aiven_client
```

Get a token from the Aiven console and log in - use your own Aiven login email
address, not mine!
```
; avn user login tony.ibbs@aiven.io --token
```

I don't want to have to specify `--project devrel-tibs` on every `avn`
command. Again, use your own project name.
```
; avn project switch devrel-tibs
```

Let's decide on a service name (again, fish shell)
```
set -x KAFKA_SERVICE_NAME tibs-button-kafka
```

Create my Kafka service.
* `google-europe-west1` has tierd storage available, which I will care about
  in a moment.
* We need at least `business-4` because we want integrations later on.
* I'm going to create my topic explicitly, but I normally use
  `--kafka.auto_create_topics_enable=true` for testing / demo purposes, as it
  can be useful. Of course, it's not a good idea in production.

```
; avn service create $KAFKA_SERVICE_NAME          \
          --service-type kafka                    \
          --cloud google-europe-west1             \
          --plan business-4                       \
          -c kafka_connect=true                   \
          -c schema_registry=true                 \
          -c kafka.auto_create_topics_enable=true
```

We may need the actual service URI later on - let's get it (still fish)
```
; set -x KAFKA_SERVICE_URI (avn service get $KAFKA_SERVICE_NAME --format '{service_uri}')
```

Check if it's running
```
; avn service get $KAFKA_SERVICE_NAME
```

and/or
```
; avn service wait $KAFKA_SERVICE_NAME
```

And download the certification files (it will create the directory if necessary)
```
; avn service user-creds-download $KAFKA_SERVICE_NAME --username avnadmin -d certs
```

```
; ls certs
ca.pem  service.cert  service.key
```

We know we're going to want to use tiered storage, so we need to enable
it for this service
```
; avn service update                  \
     $KAFKA_SERVICE_NAME              \
     -c tiered_storage.enabled=true
```

Now for our topic.
```
; set -x KAFKA_BUTTON_TOPIC button_presses
```

Note that we must specify `--partitions` and `--replication`

Because we're doing a demo, we want a short retention time, even though this
may cause inefficient use of the tiered storage (if we aren't sending a
significant number of messages). We'll choose a retention time of 5s (5,000 milliseconds), at
least for the moment.

We can always increase the number of partitions later on.


```
; avn service topic-create    \
    --partitions 3            \
    --replication 2           \
    --remote-storage-enable   \
    --local-retention-ms 5000 \
    $KAFKA_SERVICE_NAME $KAFKA_BUTTON_TOPIC
{'message': 'created'}
```

> **Note** that we can create a topic withput asking for tiered storage, and
> request it later on using `avn service topic-update`. What we can't do is
> change a topic back to not using tiered storage. If you want to do that,
> then delete the topic and recreate it (just as you'd have to do if you
> wanted to reduced the number of partitions)

## PostgreSQL setup


We need to create the target database, preferably in the same region.

```
set -x PG_SERVICE_NAME tibs-button-pg
```

A basic sort of plan should do
```
; avn service create $PG_SERVICE_NAME             \
          --service-type pg                       \
          --cloud google-europe-west1             \
          --plan hobbyist
```

and we can use our friendly wait command
```
avn service wait $PG_SERVICE_NAME
```

> **Tip** Remember we can get the connection info for our PG service with
> ```
> ; avn service connection-info pg uri $PG_SERVICE_NAME
> ```
> or, as a friendly JSON datastructure
> ```
> ; avn service get $PG_SERVICE_NAME --json | jq .service_uri_params
> ```
> and also that there's more useful stuff on the Aiven CLI (illustrated with a
> PG service) at
> [https://aiven.io/developer/aiven-cmdline](https://aiven.io/developer/aiven-cmdline).

Let's set up our target table
```
avn service cli $PG_SERVICE_NAME
```

which starts `psql` for us (you need to have `psql` installed, of course).

We'll use the default database, but we need to create a target table. We
*could* use the combination of the session id and timestamp as a primary key,
but I can't see that would give us any advantage over allow PostgreSQL to
create its own primary keys.

We're going to define an enumerated type for the action
```
CREATE TYPE action as ENUM ('EnterPage', 'PressButton');
```
We don't expect to add more actions, and even if we do, we can extend the type
later on.

```
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
```


## Sending data to PostgreSQL using the JDBC sink connector

We already specified `--c kafka-connect=true` when we created our Kafka
service, so we don't need to re-do that. Similarly, we used
`schema_registry=true` to say we're going to use the schema registry,
via Aiven for Apache Kafka's built in support for Karapace.

We need the URI for the schema registry. With bash
```
export SCHEMA_REGISTRY_URI=$(avn service get $KAFKA_SERVICE_NAME --json | jq -r '.connection_info.schema_registry_uri')
```
and with fish
```
set -x SCHEMA_REGISTRY_URI (avn service get $KAFKA_SERVICE_NAME --json | jq -r '.connection_info.schema_registry_uri')
```

Now we need to set up the sink connector configuration.

we're following the instructions at [Define a Kafka Connect configuration
file](https://docs.aiven.io/docs/products/kafka/kafka-connect/howto/jdbc-sink#define-a-kafka-connect-configuration-file).

We need the values for `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_SSL_MODE`,
`DB_USERNAME` and `DB_PASSWORD`. To find those, go to the service page for the
Postgres service in the Aiven Console, select the Overview, and look in the
Connection Information, or (as we saw earlier) retrieve them as JSON data
using
```
; avn service get $PG_SERVICE_NAME --json | jq .service_uri_params
```

We need the values `APACHE_KAFKA_HOST`, `SCHEMA_REGISTRY_PORT`,
`SCHEMA_REGISTRY_USER` and `SCHEMA_REGISTRY_PASSWORD`. To find those, go to
the service page for the Kafka service in the Aiven Console, select the
Overview, and look in the Schema Registry tab of the Connection Information,
or retrieve them as JSON data using
```
; avn service get $KAFKA_SERVICE_NAME --json | jq '.components | map(select(.component == "schema_registry"))'
```
for the connection details, and
```
; avn service get $KAFKA_SERVICE_NAME --json | jq .users[0].username
```
```
; avn service get $KAFKA_SERVICE_NAME --json | jq .users[0].password
```
for the username and password.

We use those values to create a file called `pg_avro_sink.json`, using the following as a template:

```json
{
    "name":"sink_button_presses_avro_karapace",
    "connector.class": "io.aiven.connect.jdbc.JdbcSinkConnector",
    "topics": "button_presses",
    "connection.url": "jdbc:postgresql://DB_HOST:DB_PORT/DB_NAME?sslmode=SSL_MODE",
    "connection.user": "DB_USERNAME",
    "connection.password": "DB_PASSWORD",
    "tasks.max":"1",
    "auto.create": "false",
    "auto.evolve": "false",
    "insert.mode": "insert",
    "delete.enabled": "false",
    "pk.mode": "none",
    "key.converter": "io.confluent.connect.avro.AvroConverter",
    "key.converter.schema.registry.url": "https://APACHE_KAFKA_HOST:SCHEMA_REGISTRY_PORT",
    "key.converter.basic.auth.credentials.source": "USER_INFO",
    "key.converter.schema.registry.basic.auth.user.info": "SCHEMA_REGISTRY_USER:SCHEMA_REGISTRY_PASSWORD",
    "value.converter": "io.confluent.connect.avro.AvroConverter",
    "value.converter.schema.registry.url": "https://APACHE_KAFKA_HOST:SCHEMA_REGISTRY_PORT",
    "value.converter.basic.auth.credentials.source": "USER_INFO",
    "value.converter.schema.registry.basic.auth.user.info": "SCHEMA_REGISTRY_USER:SCHEMA_REGISTRY_PASSWORD"
}
```

1. We've set the `name` of the connector to indicate we're using Avro and
   Karapace

2. The value for `topics` needs to match the topic we created, and that we use
   in our source code - that is `button_presses`

   We take care to use underscores rather than hyphens in the name because we
   want it to match the Avro schema name, and Avro names don't allow hyphens.

3. By default, the table written to will have the same name as the topic. The
   topic name `button_presses` is a legal PostgreSQL table name, so we
   don't need to specify `"table.name.normalize": "true"`.

4. The value for `pk.mode` is `none`, which means that we aren't using any of
   the values from the message as the database record key.

5. We set `auto.create` to `false` because we have already created our target
   table, and don't need it creating for us. Similarly, we set `auto.evolve`
   to `false` because we don't want its schema to be changed for us.

6. We set `insert.mode` to `"insert"` because we should only be inserting new
   records. For PostgreSQL,
   [`upsert`](https://github.com/aiven/jdbc-connector-for-apache-kafka/blob/master/docs/sink-connector.md#upsert-mode)
   would do `INSERT .. ON CONFLICT .. DO UPDATE SET ..`, which will update a
   row if it already exists. In theory we don't want that, as each order shoud
   be unique. In practice, for a demo, this might actually be a problem, as
   restarting the demo program will restart `count` from 0 again. We'll see
   what happens in practice.

All the upper case values come from appropriate places in the Aiven
Console, or can be found using `avn service` commands, *with the
exception of `USER_INFO`, which is meant to be left as it is*.

----

Once all of that is set up, we can create our sink connector
```
; avn service connector create $KAFKA_SERVICE_NAME @pg_avro_sink.json
```

To get a list of the service connectors (as a JSON structure) attached to this Kafka, use:
```shell
avn service connector list $KAFKA_SERVICE_NAME
```

To find out more about the connector, go to the [Aiven console](https://console.aiven.io/) and the service
page for our Kafka, and look at the **Connectors** tab. If there are errors,
then you'll see a warning triangle symbol next to the "Tasks" value for the
connector, and clicking on that will give the Java stacktrace.

We can check the status of the connector as follows:
```shell
avn service connector status $KAFKA_SERVICE_NAME sink_button_presses_avro_karapace
```

And *now* we can try running our data generation program again
```
src/generate_data.py
```

and see messages appearing in the Kafka topic, in Avro format, and they should
also be visible in the database with:
```
SELECT * FROM button_presses;
```

## The Avro schema

In the Python source code, we define the Avro schema, which we register with
Karapace.

We use the following Python code (which then gets dumped to a JSON string
before it is registered with Karapace)
```python
    schema = {
        'doc': 'Web app interactions',
        'name': topic_name,
        'type': 'record',
        'fields': [
            {'name': 'session_id', 'type': 'string', 'logicalType': 'uuid'},
            {'name': 'timestamp', 'type': 'long', 'logicalType': 'timestamp-micros'},
            {'name': 'action', 'type': 'string'},
            {'name': 'country_name', 'type': 'string'},
            {'name': 'country_code', 'type': 'string'},
            {'name': 'subdivision_name', 'type': 'string'},
            {'name': 'subdivision_code', 'type': 'string'},
            {'name': 'city_name', 'type': 'string'},
            {'name': 'cohort', 'type': ['null', 'int'], 'default': None},
        ],
    }
```

The [Avro specification](https://avro.apache.org/docs/1.11.1/specification/)
describes the data type it supports, and the [logical
types](https://avro.apache.org/docs/1.11.1/specification/#logical-types).

Notes:
* Using a UUID as a "session" id makes sense
* We're using a UNIX timestamp (microseconds since the epoch). If we were only
  sending data to PostgreSQL, we could probably use a full ISO 8601
  string, with timezone information, but (a) that's a lot more data and (b)
  when we get to ClickHouse reading the same messages, we'll see that it
  doesn't understand how to decode those text strings into a timestamp.
* The `cohort` field is nullable. Because this is Python code, the `'default'`
  is specified as `None`, which will get converted to an appropriate `null`
  value in the actual data.
* We do not send the IP address of the page visitor anywhere - only data
  dervived from that IP address.

## Running the fake data generator

In the main directory:
```
src/generate_data.py
```

This will generate an EnterPage event and then a random number of ButtonPress
events from a "session" at a random IP address. The `cohort` value will be `null`.

The fake generator and the web app share code for creating and sending messages.

## Running the web app

When you start the app
```
fastapi dev src/app.py
```
(or, for more production-y use, `fastapi run src/app.py`)

If you're running it locally, you can go to the initial page at
http://localhost:8000/, which has a button.

An EnterPage Kafka message will also be sent, containing a "session" UUID and information
derived from the IP address of the viewer.

> **Note** that at the moment, if that IP address is actually 127.0.0.1
> (localhost) then a fake IP address will be generated instead.

The "session" id and location information will also be saved in a cookie.

When you press the button, a ButtonPress event will be sent.

If you want to clear the cookies, go to http://localhost:8000/reset (or the
equivalent if the app is not running locally).
There's a convenient link there to go back to the main page :)

Note that we don't have any "this app is using cookies" disclaimer - I don't
believe we need such, but maybe should check :(

Lots of stuff is logged, so you can tell what is going on.

## Sending data to ClickHouse using the ClickHouse integration

```
set -x CH_SERVICE_NAME tibs-button-ch
```

Remember

* We want to be in the same region as the Kafka service, `google-europe-west1`
* We want to use an integration to connect Kafka to ClickHouse, and [Create a
  ClickHouse sink connector for Aiven for Apache
  Kafka®](https://aiven.io/docs/products/kafka/kafka-connect/howto/clickhouse-sink-connector)
  points out that "Aiven for ClickHouse service integrations are available for
  Startup plans and higher."
* In that region, the smallest Startup plan is `startup-16`
  ```
  ; avn service plans --service-type clickhouse --cloud google-europe-west1
  ClickHouse - Fast resource-effective data warehouse for analytical workloads Plans:

      clickhouse:hobbyist            $0.233/h  Hobbyist (1 CPU, 4 GB RAM, 180 GB disk)
      clickhouse:startup-16          $0.685/h  Startup-16 (2 CPU, 16 GB RAM, 1150 GB disk)
      clickhouse:startup-32          $1.370/h  Startup-32 (4 CPU, 32 GB RAM, 2300 GB disk)
      clickhouse:startup-64          $2.740/h  Startup-64 (8 CPU, 64 GB RAM, 4600 GB disk)
      ...
  ```

So let's create the service
```
; avn service create $CH_SERVICE_NAME          \
          --service-type clickhouse            \
          --cloud google-europe-west1          \
          --plan startup-16
```

And we can wait as usual
```
; avn service wait $CH_SERVICE_NAME
```

Once that's running, we're going to follow (more or lesss)
[Connecting Apache Kafka® and Aiven for
ClickHouse®](https://aiven.io/developer/connecting-kafka-and-clickhouse)

First create the integration

```
avn service integration-create            \
    --integration-type clickhouse_kafka   \
    --source-service $KAFKA_SERVICE_NAME\
    --dest-service $CH_SERVICE_NAME
```

To check that worked we do:
```
; avn service integration-list $CH_SERVICE_NAME | grep $KAFKA_SERVICE_NAME


(integration not enabled)             tibs-button-ch     tibs-button-kafka  kafka_logs              false    false   Send service logs to an Apache Kafka service or an external Apache Kafka cluster
ce2f14fb-68c1-46ee-8be2-181b4acf515b  tibs-button-kafka  tibs-button-ch     clickhouse_kafka        true     true    Send and receive data between ClickHouse and Apache Kafka services
```

which shows we've got a Kafka to ClickHouse integration running.

Without the `grep` we get another row, and column headings:
```
; avn service integration-list $CH_SERVICE_NAME
SERVICE_INTEGRATION_ID                SOURCE             DEST               INTEGRATION_TYPE        ENABLED  ACTIVE  DESCRIPTION
====================================  =================  =================  ======================  =======  ======  ================================================================================
(integration not enabled)             tibs-button-ch     tibs-button-ch     clickhouse_credentials  false    false   Add remote data source credentials to be used in ClickHouse service
(integration not enabled)             tibs-button-ch     tibs-button-kafka  kafka_logs              false    false   Send service logs to an Apache Kafka service or an external Apache Kafka cluster
ce2f14fb-68c1-46ee-8be2-181b4acf515b  tibs-button-kafka  tibs-button-ch     clickhouse_kafka        true     true    Send and receive data between ClickHouse and Apache Kafka services
```

We're going to need that service integration id, so let's leverage the
`--json` output available with `avn` commands. After playing around with `jq`
a bit, we get the following. The `-r` (`--raw-output`) is to stop the string
value returned from having double quotes round it.

```
set -x KAFKA_CH_SERVICE_INTEGRATION_ID (avn service integration-list $CH_SERVICE_NAME --json | jq -r '. | map(select(.integration_type == "clickhouse_kafka"))[0].service_integration_id')
```


We can check that worked!
```
; echo $KAFKA_CH_SERVICE_INTEGRATION_ID
"ce2f14fb-68c1-46ee-8be2-181b4acf515b"
```


We now need to say what we want the integration to do. The tutorial we've been
following uses in-line JSON on the command line, but I think it's easier to
create a JSON file instead. We'll call it `kafka-ch-integration-config.json`
and it should contain
```json
{
    "tables": [
        {
            "name": "button_presses_from_kafka",
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
            "topics": [{"name": "button_presses"}],
            "data_format": "AvroConfluent",
            "group_name": "button_presses_from_kafka_consumer"
        }
    ]
}
```

Notes on the above:
* We specify which topic to read from, using `topics`
* The data format is `AvroConfluent` - this is the same "Avro message with a
  schema id at the front" we're already writing to Kafka.
* The ClickHouse document
  [AvroConfluent](https://clickhouse.com/docs/interfaces/formats/AvroConfluent)
  describes how to match Avro and ClickHouse datatypes in the table we're
  going to be writing to:
  * The logical `UUID` "session_id" maps directly to a `UUID`
  * The logical `timestamp_micros` "timestamp" maps directly to `
    DateTime64(6)` - I assume the `(6)` means there are 6 digits of fractional
    second, that is, microseconds.
  * The nullable "cohort" maps to a `Nullable(Smallint)`
* And that table will be called `button_presses_from_kafka`

Now we can update the integration with all of that information.
```
avn service integration-update \
    $KAFKA_CH_SERVICE_INTEGRATION_ID \
    --user-config-json @kafka-ch-integration-config.json
```

That will create a "service" table in ClickHouse. The Aiven integration will
already have set that table to know where the Karapace schema is, so it's all
ready to read our Kafka messages.

To see what ClickHouse is doing, I want the ClickHouse CLI.
See [ClickHouse Client](https://clickhouse.com/docs/interfaces/cli) for
options on install it.

There *is* a homebrew option (`brew install --cask clickhouse`), but it's not
mentioned on the ClickHouse web site, so I do what *that* advises
```
; curl https://clickhouse.com/ | sh
```

which puts the `clickhouse` binary in my current directory, from where I
copied it into one of my `PATH` directories.
(Note that the "official" method also installs a more up-to-date version of the command -
25.3.1.1803 versus 25.2.1.3085-stable from homebrew).

To get the information needed to connect to our ClickHouse service:
```
; avn service get $CH_SERVICE_NAME --json | jq .service_uri_params
```

and then
```
./clickhouse client \
    --host <HOST> --port <PORT> \
    --user avnadmin --password <PASSWORD> \
    --secure
```

I can use `show databases` to show the databases, including the "service"
database that was created by the integration:
```
SHOW DATABASES

Query id: 4a20ffad-4dc4-41bf-b6ba-ac152436fc8f

Connecting to tibs-button-ch-devrel-tibs.b.aivencloud.com:10143 as user avnadmin.
Connected to ClickHouse server version 24.8.13.

   ┌─name──────────────────────┐
1. │ INFORMATION_SCHEMA        │
2. │ default                   │
3. │ information_schema        │
4. │ service_tibs-button-kafka │
5. │ system                    │
   └───────────────────────────┘

5 rows in set. Elapsed: 0.001 sec.
```

If I generate some fake data using `src/generate_data.py`
and
```
select * from `service_tibs-button-kafka`.button_presses_from_kafka
```

then after a bit, there's my data! - for instance
```
SELECT *
FROM `service_tibs-button-kafka`.button_presses_from_kafka

Query id: 46337714-24e9-4a89-883c-4f88b58812ca

   ┌─session_id───────────────────────────┬──────────────────timestamp─┬─action──────┬─country_name─┬─country_code─┬─subdivision_name─┬─subdivision_code─┬─city_name─┬─cohort─┐
1. │ 8b6f3882-7d99-4782-9731-82d411ec7ecf │ 2025-03-13 15:23:17.396751 │ PressButton │ China        │ CN           │                  │                  │           │   ᴺᵁᴸᴸ │
2. │ 8b6f3882-7d99-4782-9731-82d411ec7ecf │ 2025-03-13 15:23:19.851751 │ PressButton │ China        │ CN           │                  │                  │           │   ᴺᵁᴸᴸ │
3. │ 8b6f3882-7d99-4782-9731-82d411ec7ecf │ 2025-03-13 15:23:23.342751 │ PressButton │ China        │ CN           │                  │                  │           │   ᴺᵁᴸᴸ │
4. │ 8b6f3882-7d99-4782-9731-82d411ec7ecf │ 2025-03-13 15:23:13.264751 │ EnterPage   │ China        │ CN           │                  │                  │           │   ᴺᵁᴸᴸ │
   └──────────────────────────────────────┴────────────────────────────┴─────────────┴──────────────┴──────────────┴──────────────────┴──────────────────┴───────────┴────────┘

4 rows in set. Elapsed: 3.505 sec.
```

Now I need to create the target table. Here we can describe our timestamp as
`DateTime(UTC)`, which is a more familiar datatype from the ClickHouse
[DateTime](https://clickhouse.com/docs/sql-reference/data-types/datetime)
documentation (but ClickHouse knows how to "convert")

```
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
ORDER BY timestamp
```

We then need a materialised view to get data from the service table to our
target table
```
CREATE MATERIALIZED VIEW materialised_view TO button_presses AS
SELECT * FROM `service_tibs-button-kafka`.button_presses_from_kafka;
```

And now we can look for our data in the target table

```
select * from button_presses
```

which outputs something like
```
SELECT *
FROM button_presses

Query id: bc25838b-e3b4-413b-acd6-392622b62231

    ┌─session_id───────────────────────────┬───────────timestamp─┬─action──────┬─country_name──┬─country_code─┬─subdivision_name─┬─subdivision_code─┬─city_name─┬─cohort─┐
 1. │ 0fa48496-efe3-454b-a1de-99dfdfc49196 │ 2025-03-13 15:48:19 │ EnterPage   │ United States │ US           │ Massachusetts    │ MA               │ Cambridge │   ᴺᵁᴸᴸ │
 2. │ 0fa48496-efe3-454b-a1de-99dfdfc49196 │ 2025-03-13 15:48:23 │ PressButton │ United States │ US           │ Massachusetts    │ MA               │ Cambridge │   ᴺᵁᴸᴸ │
 3. │ 0fa48496-efe3-454b-a1de-99dfdfc49196 │ 2025-03-13 15:48:24 │ PressButton │ United States │ US           │ Massachusetts    │ MA               │ Cambridge │   ᴺᵁᴸᴸ │
 4. │ 0fa48496-efe3-454b-a1de-99dfdfc49196 │ 2025-03-13 15:48:25 │ PressButton │ United States │ US           │ Massachusetts    │ MA               │ Cambridge │   ᴺᵁᴸᴸ │
 5. │ 0fa48496-efe3-454b-a1de-99dfdfc49196 │ 2025-03-13 15:48:30 │ PressButton │ United States │ US           │ Massachusetts    │ MA               │ Cambridge │   ᴺᵁᴸᴸ │
 6. │ 0fa48496-efe3-454b-a1de-99dfdfc49196 │ 2025-03-13 15:48:31 │ PressButton │ United States │ US           │ Massachusetts    │ MA               │ Cambridge │   ᴺᵁᴸᴸ │
 7. │ 0fa48496-efe3-454b-a1de-99dfdfc49196 │ 2025-03-13 15:48:34 │ PressButton │ United States │ US           │ Massachusetts    │ MA               │ Cambridge │   ᴺᵁᴸᴸ │
 8. │ 6a928093-ee61-4d0d-90be-9ab1fc99da4f │ 2025-03-13 15:50:55 │ EnterPage   │ United States │ US           │ Iowa             │ IA               │ Akron     │   ᴺᵁᴸᴸ │
 9. │ 6a928093-ee61-4d0d-90be-9ab1fc99da4f │ 2025-03-13 15:50:58 │ PressButton │ United States │ US           │ Iowa             │ IA               │ Akron     │   ᴺᵁᴸᴸ │
10. │ 6a928093-ee61-4d0d-90be-9ab1fc99da4f │ 2025-03-13 15:51:01 │ PressButton │ United States │ US           │ Iowa             │ IA               │ Akron     │   ᴺᵁᴸᴸ │
    └──────────────────────────────────────┴─────────────────────┴─────────────┴───────────────┴──────────────┴──────────────────┴──────────────────┴───────────┴────────┘

10 rows in set. Elapsed: 0.002 sec.
```
