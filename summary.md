# Summary - getting things to run

## General setup

```
; python -m venv venv
; source venv/bin/activate.fish    # why yes, I use the fish shell
; pip install -r requirements.txt
```

## Kafka setup

For the moment, I'm going to do things with the `avn` command

I already did the following in the previous section

```
; python -m venv venv
; source venv/bin/activate.fish    # why yes, I use the fish shell
; pip install -r requirements.txt
```

Make sure I have `avn`, and upgrade it if necessary
```
; pip install -U aiven_client
```

Get a token from the Aiven console and log in
```
; avn user login tony.ibbs@aiven.io --token
```

I don't want to have to specify `--project devrel-tibs` on every `avn` command:
```
; avn project switch devrel-tibs
```

Let's decide on a servicen name (again, fish shell)
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

Now for our topic.
```
; set -x KAFKA_BUTTON_TOPIC button_presses
```

Note that we must specify `--partitions` and `--replication`
```
; avn service topic-create  \
    --partitions 3          \
    --replication 2         \
    $KAFKA_SERVICE_NAME $KAFKA_BUTTON_TOPIC
{'message': 'created'}
```

We can always increase the number of partitions later on.

We know we're going to want tiered storage for our topic, so we need to enable
it for this service
```
; avn service update                  \
     $KAFKA_SERVICE_NAME              \
     -c tiered_storage.enabled=true
```

and then we can set it up for this topic (we could also have done this when we
*created* the topic, using the same `--remote-storage-enable` switch).

Because we're doing a demo, we want a short retention time, even though this
may cause inefficient use of the tiered storage (if we aren't sending a
significant number of messages). We'll choose a retention time of 5s (5,000 milliseconds), at
least for the moment.
```
; avn service topic-update \
    --service-name $KAFKA_SERVICE_NAME \
    --topic $KAFKA_BUTTON_TOPIC        \
    --remote-storage-enable            \
    --local-retention-ms 5000
```

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

which starts `psql` for us

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
    "timestamp" char(32) not null,
    "cohort" smallint,
    "action" text not null,
    "country_name" text not null,
    "country_code" char(2) not null,
    "subdivision_name" text,
    "subdivision_code" text,
    "city_name" text
);
```


## Connectors

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

## Running the web app

In the main directory:
```
fastapi dev src/app.py
```

(or, for more production-y use, `fastapi run src/app.py`)


## How the app works

When you start the app
```
fastapi dev src/app.py
```

you can go to the initial page at http://localhost:8000/, which has a button.

An EnterPage Kafka message will also be sent, containing a "session" UUID and information
derived from the IP address of the viewer.

> **Note** that at the moment, if that IP address is actually 127.0.0.1
> (localhost) then a fake IP address will be generated instead.

The "session" id and location information will also be saved in a cookie.

When you press the button, a ButtonPress event will be sent.

If you want to clear the cookies, go to http://localhost:8000/reset

There's a convenient link there to go back to the main page :)

Note that we don't have any "this app is using cookies" message - I don't
believe we need such, but maybe should check :(

Lots of stuff is logged, so you can tell what is going on.

To send fake data, you can still run `src/generate_data.py` (it will give help
if you pass `--help`). It and the app use the same code to create the messsages.
