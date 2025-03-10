# Kafka connectors

> **Note** Check whether we need to display an attribution for use of the data
> from Maxmind. I'm thinking of this after reading the README at
> https://github.com/sapics/ip-location-db

## Plan of action

This is to play with some of the connector stuff we want to do for our Kafka
button app

Let's look at

1. Creating an Aiven for Apache Kafka® service
2. Creating fake button press data
3. Sending it to that Kafka
4. Creating an Aiven for PostgreSQL® service
5. Connecting Kafka to PG and getting the data into PG
6. Creating an Aiven for Grafana service
7. Connecting that to Kafka and seeing what we can see about the data

I'll use the command line first, because it's easiest for me.

Ideally we'd then document doing stuff using the console, and especially with terraform.

...actually, I'm writing the fake data app first - see `src/generate_data.py`
for progress

## Fake data script

[`src/generate_data.py`](src/generate_data.py)

Fake data script now knows how to create fake data values, but isn't yet
talking to Kafka.

Notes:
* To get city name from an IP address, we need to download an extra dataset,
  but luckily that can be automated, and only done when the dataset has not
  already been downloaded.
* The downloaded dataset gets cached with the library in `venv/lib/python3.11/site-packages/geoip2fast/`
* We're using `geoip2fast-city-ipv6.dat.gz`
* Determining the lat, long for a city would need a web query, so that's
  probably (at least for now) best left to the client / consumer.
* The script is currently generating fake IP addresses with geoip2fast itself.
  The DOWNSIDE of that is that the geoip2fast methods only generate IP
  addresses that exist in the GeoIP2Fast data files, so we won't get any
  unrecognised addresses.
 
  We could go back to using Faker, but then we get a lot more unrecognised locations.

* The lat/long fields in the JSON data are interesting - presumably this is a
  future possibility? - unfortunately it doesn't seem to be supported by any
  of the available data files.
  
  ...ah, it looks as if lat/long may be something that gets added to city info
  for data version 121, which is a setting from the data file itself, and gets
  returned as part of the `get_database_info` method.

```
; python -m venv venv
; source venv/bin/activate.fish    # why yes, I use the fish shell
; pip install -r requirements.txt
```

At the moment, the script is just printing stuff out
```
; src/generate_data.py
Database info:
{'database_content': 'Country + City with IPv4 and IPv6',
 'database_fullpath': '/Users/tony.ibbs/sw/aiven/Aiven-Labs/kafka-button-app/venv/lib/python3.11/site-packages/geoip2fast/geoip2fast-city-ipv6.dat.gz',
 'file_size': 14635455,
 'uncompressed_file_size': 80909989,
 'source_info': 'MAXMIND:GeoLite2-City-IPv4IPv6-en-20250228',
 'dat_version': 120,
 'city': {'main_index_size': 50070,
          'first_ip_list_size': 5006990,
          'city_names_id_list_size': 5006990,
          'netlength_list_size': 5006990,
          'country_names': 268,
          'city_names': 77730,
          'ipv4_networks': 3267030,
          'ipv6_networks': 1739960,
          'number_of_chunks': 50070,
          'chunk_size': 100}}
INFO:root:Session e0569750-8c8e-42a8-83fd-d9ad310162b5
INFO:root:IP 199.250.231.120 -> United States, US (Nahunta, Georgia, GA
{
   "ip": "199.250.231.120",
   "country_code": "US",
   "country_name": "United States",
   "city": {
      "name": "Nahunta",
      "subdivision_code": "GA",
      "subdivision_name": "Georgia",
      "latitude": null,
      "longitude": null
   },
   "cidr": "199.250.224.0/20",
   "hostname": "",
   "asn_name": "",
   "asn_cidr": "",
   "is_private": false,
   "elapsed_time": "0.000060584 sec"
}
INFO:root:Press 0 at 1741175477.503385
INFO:root:Press 1 at 1741178088.503385
INFO:root:Press 2 at 1741181168.503385
INFO:root:Press 3 at 1741183990.503385
INFO:root:Press 4 at 1741185172.503385
INFO:root:Press 5 at 1741187857.503385
INFO:root:Press 6 at 1741191683.503385
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


## Fake data script 2

The script now uses `aiokafka` to generate button presses for a single web
page interaction. And the messages get into the topic, and tiered storage is
being used.


## At the end of the day

Let's not waste resources
```
; avn service update $KAFKA_SERVICE_NAME --power-off
```

## Changing to Avro messages

If we're going to sink to PG with a JDBC connector, then our messages need to
contain schema information.

If we stick with JSON messages, then *every message* will need to have a JSON
schema attached to it, which is quite wasteful.

So instead we shall change to using Avro, and then we just need to send the
schema id (plus a byte...)

> **Note** lots of inspiration taken from the code in
> https://github.com/Aiven-Labs/fish-and-chips-and-kafka/tree/main/src
> which addresses this exact thing in demo 6 (in the "homework" section)

## Let's sink!

Remembering our Avro schema:

```
# REMEMBER to double check that the optional fields work as we expect
AVRO_SCHEMA = {
    'doc': 'Web app interactions',
    'name': TOPIC_NAME,
    'type': 'record',
    'fields': [
        {'name': 'session_id', 'type': 'string'},
        {'name': 'timestamp', 'type': 'long'},
        {'name': 'action', 'type': 'string'},
        {'name': 'country_name', 'type': 'string'},
        {'name': 'country_code', 'type': 'string'},
        {'name': 'subdivision_name', 'type': ['null', 'string'], 'default': null},
        {'name': 'subdivision_code', 'type': ['null', 'string'], 'default': null},
        {'name': 'city_name', 'type': ['null', 'string'], 'default': null},
    ],
}
```

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

## Message design

The message content has been evolving as I think about it - here's the current
design:

* **session_id** is a UUID that identifies the session using the web app. This
  allows us to group the events taken by the user during that session. A UUID
  is a fairly traditional solution for this. For simplicity, we use the
  traditional string representation (for instance
  `afd52111-9f40-4c62-80cc-d91c121e470a`) even though those hyphens are
  strictly redundant.
* **timestamp** says when the event happened, in UTC. We represent this as a string using
  the standard ISO 8601 format (for instance `2025-03-07T10:33:46.754240+00:00`),
  because that's the most unabmiguous way of doing it, even if it's longer
  than, for instance, a Unix timestamp. It makes it very clear what timezone
  the timestamp is in, and also doesn't require people to figure out whether
  the Unix timestemp they've been given is in seconds or milliseconds or
  microseconds since the epoch.
* **action** is a string, one of `EnterPage`, `PressButton` or `ExitPage`. We
  could use small integers, but the string is easier to understand.
* **count** is an integer, starting at 0, representing the sequence of the
  event in the session. This was added at the suggestion of one of our interns
  (no, actually it was me) because the `count` for the `ExitPage` event says
  how many events there were in that session. This means we can tell if we've
  got all of the events for the session - there should be that number. 

  We might care about this because events don't always arrive in order
  (because internet), so we might receive the `ExitPage` before we've got all
  the other events, and also because sometimes events get lost (again, because
  internet), in which case the `count` on individual items allows us to know
  which events were lost.
 
  Is this useful information? Well, if we don't collect it, we won't be able
  to use it.
 
  One small caution - we're using an integer for this, so there's a built-in
  (but unspecified) assumption of the maximum number of events in a session.
  We do not define what happens if that integer gets too big.

Then we get the location date that is looked up using the geoip2fast package.
We can do this once at the start of our web session. See
https://github.com/rabuchaim/geoip2fast for more information. Remember that
the information determined is, by its nature, approximate, and that not all IP
addresses will give useful values.

* **country_name** is the name of the country where the IP address appears to
  be located, or some other string (for instance, for private networks, or if
  the IP address is not in the database).
* **country_code** is the two letter ISO code for the country, or `--`.
* **subdivision_name** is the "subdivision" code - for the USA, this might be
  a state. This may be unset (`null`).
* **subdivision_code** is a two letter code for that subdivision. This may be
  unset (`null`).
* **city_name** is the name of the city where the IP address appears to be
  located. This may be unset (`null`).

Things that aren't there
* We don't put the actual IP address in the message, as that counts as
  personal information, and thus we want to redact it.
* We don't put latitude and longitude data (representing the approximate
  location) because the current version of geoip2fast doesn't provide it, and
  because looking it up would require an internet query, which we'd rather not
  do. And in practice we'd also need to maintain our own cache of country ->
  lat, long and city -> lat, long, because we might need to make a *lot* of
  such queries, and the upstream service would justifiably want us to rate
  limit. That all means we want to defer that to the far end, because after
  all the data user might not even want that information.

  (If geoip2fast becomes able to return approximate lat, long values, then
  this balance changes.)

## Back to schema wrangling

Now we know the actual message content, we can plan our PG table and use
Karapace and so on.

Still being inspired by
https://github.com/Aiven-Labs/fish-and-chips-and-kafka/tree/main/src#write-to-postgresql-with-a-jdbc-kafka-connector-avro-and-karapace

Remember we can get the connection info for our PG service with
```
; avn service connection-info pg uri $PG_SERVICE_NAME
```
or, as a friendly JSON datastructure
```
; avn service get $PG_SERVICE_NAME --json | jq .service_uri_params
```

and also that there's more useful stuff on the Aiven CLI (illustrated with a
PG service) at
[https://aiven.io/developer/aiven-cmdline](https://aiven.io/developer/aiven-cmdline).

----

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
CREATE TYPE action as ENUM ('EnterPage', 'PressButton', 'ExitPage');
```
We don't expect to add more actions, and even if we do, we can extend the type
later on.

```
CREATE TABLE button_presses (
  "id" bigint generated always as identity primary key,
  "session_id" uuid not null,
  "timestamp" timestamp with time zone not null,
  "action" action not null,
  "count" bigint not null,
  "country_name" text not null,
  "country_code" char(2) not null,
  "subdivision_name" text,
  "subdivision_code" text,
  "city_name" text
);
```

Notes:
* We deliberately choose the same table name as the Kafka topic - this makes
  things easier later on.
* The use of `bigint generated always as identity` seems to be the new way of
  doing `serial` - it's more explicit and has more guarantees.
* I've used the standard SQL `timestamp with time zone` rather than the PG
  abbreviation `timestamptz`
  
And the result is
```
defaultdb=> \d button_presses
                                   Table "public.button_presses"
      Column      |           Type           | Collation | Nullable |           Default
------------------+--------------------------+-----------+----------+------------------------------
 id               | bigint                   |           | not null | generated always as identity
 session_id       | uuid                     |           | not null |
 timestamp        | timestamp with time zone |           | not null |
 action           | action                   |           | not null |
 count            | bigint                   |           | not null |
 country_name     | text                     |           | not null |
 country_code     | character(2)             |           | not null |
 subdivision_name | text                     |           |          |
 subdivision_code | text                     |           |          |
 city_name        | text                     |           |          |
Indexes:
    "button_presses_pkey" PRIMARY KEY, btree (id)
```

where
```
defaultdb=> \dT+ action
                                        List of data types
 Schema |  Name  | Internal name | Size |  Elements   |  Owner   | Access privileges | Description
--------+--------+---------------+------+-------------+----------+-------------------+-------------
 public | action | action        | 4    | EnterPage  +| avnadmin |                   |
        |        |               |      | PressButton+|          |                   |
        |        |               |      | ExitPage    |          |                   |
(1 row)
```
or also
```
defaultdb=> select unnest(enum_range(null::action));
   unnest
-------------
 EnterPage
 PressButton
 ExitPage
(3 rows)
```

Now to get thingsl linked up.

We already specified `--c kafka-connect=true` when we created our Kafka
service, so we don't need to re-do that. Similarly, we used
`schema_registry=true` to say we're going to use the schema registry,
via Aiven for Apache Kafka's built in support for Karapace.

In fact, let's do a summary. We're going to be using
* Aiven for Apache Kafka to stream our data
* Aiven for PostgreSQL to received data
* The
  [`io.aiven.connect.jdbc.JdbcSinkConnector`](https://github.com/aiven/jdbc-connector-for-apache-kafka/blob/master/docs/sink-connector.md),
  to consume data from Kafka and write it to PostgreSQL. This is an Apache 2 licensed fork of the Confluent
  [`kafka-connect-jdbc`](https://github.com/confluentinc/kafka-connect-jdbc)
  sink connector, from before it changed license (the Confluent connector is
  no longer Open Source).
* [Karapace](https://www.karapace.io/), The open source schema repository for
  Kafka, to store the schema we use for the messages
* [Apache Avro™](https://avro.apache.org/) to serialize the messages. To each
  message we'll also add the schema id.
* The
  [`io.confluent.connect.avro.AvroConverter`](https://github.com/confluentinc/schema-registry/blob/master/avro-converter/src/main/java/io/confluent/connect/avro/AvroConverter.java)
  connector to understand that added schema id, allowing the connector look up
  the schema and understand how to write the message data to Postgres. Note
  that the source code for that connector is open source, under the Apache License, Version 2.0.

I think the easiest way to unpick that is to look at the code :)

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

and see messages appearing in the Kafka topic, in Avro format, but not yet in
the database.

> **Problem**
> In the JDBC connector, it receieves the `timestamp` field as a string, but
> doesn't know how to write that to the PostgreSQL column, which has type
> `TIMESTAMP`. As the traceback says:
> ```
>  ERROR: column "timestamp" is of type timestamp with time zone but expression is of type character varying
>  Hint: You will need to rewrite or cast the expression.
> ```

Searching around this appears to be a known problem. The "obvious" solutions
appear to involve writing functions in PostgreSQL itself to do the
transformation, which is a bit overkill for our needs. So for the moment we'll
revert the column type to a string. We can always re-address the "string or
integer timestamp" issue later on if we need to.

And of course, much the same applies to the `action` column.

```
DROP TABLE button_presses;
CREATE TABLE button_presses (
    "id" bigint generated always as identity primary key,
    "session_id" uuid not null,
    "timestamp" char(32) not null,
    "action" text not null,
    "count" bigint not null,
    "country_name" text not null,
    "country_code" char(2) not null,
    "subdivision_name" text,
    "subdivision_code" text,
    "city_name" text
);
```

But once we've done those changes, and re-run the program, we see lots of
data, including that from earlier runs of the program (since the data was
still in Kafka)
```
defaultdb=> select * from button_presses;
 id |              session_id              |            timestamp             |   action    | count | country_name  | country_code | subdivision_name | subdivision_code | city_name
----+--------------------------------------+----------------------------------+-------------+-------+---------------+--------------+------------------+------------------+-----------
  1 | f7447f58-7819-4063-9dfc-c56c29b9c9e9 | 2025-03-07T16:31:48.753993+00:00 | PressButton |     1 | France        | FR           | Île-de-France    | IDF              | Plaisir
  2 | f7447f58-7819-4063-9dfc-c56c29b9c9e9 | 2025-03-07T16:31:57.570993+00:00 | ExitPage    |     3 | France        | FR           | Île-de-France    | IDF              | Plaisir
  3 | f7447f58-7819-4063-9dfc-c56c29b9c9e9 | 2025-03-07T16:31:46.664993+00:00 | EnterPage   |     0 | France        | FR           | Île-de-France    | IDF              | Plaisir
  4 | f7447f58-7819-4063-9dfc-c56c29b9c9e9 | 2025-03-07T16:31:53.054993+00:00 | PressButton |     2 | France        | FR           | Île-de-France    | IDF              | Plaisir
  5 | 477c54cd-5155-422e-a1bf-81e1f1900feb | 2025-03-07T16:39:35.446666+00:00 | EnterPage   |     0 | United States | US           |                  |                  |
  6 | 477c54cd-5155-422e-a1bf-81e1f1900feb | 2025-03-07T16:39:36.049666+00:00 | PressButton |     1 | United States | US           |                  |                  |
  7 | 477c54cd-5155-422e-a1bf-81e1f1900feb | 2025-03-07T16:39:36.986666+00:00 | ExitPage    |     2 | United States | US           |                  |                  |
  8 | e1a06fd1-55b9-4928-8820-2e47a664563d | 2025-03-07T16:48:41.102072+00:00 | ExitPage    |     2 | United States | US           | California       | CA               |
  9 | 4660b366-4a68-490b-b77f-55702c863884 | 2025-03-07T16:56:28.462838+00:00 | PressButton |     3 | United States | US           | Wyoming          | WY               | Cheyenne
 10 | 4660b366-4a68-490b-b77f-55702c863884 | 2025-03-07T16:56:36.833838+00:00 | PressButton |     6 | United States | US           | Wyoming          | WY               | Cheyenne
 11 | 4660b366-4a68-490b-b77f-55702c863884 | 2025-03-07T16:56:45.421838+00:00 | ExitPage    |     9 | United States | US           | Wyoming          | WY               | Cheyenne
 12 | 5fe640e8-a285-4bcb-8766-5f5be1f96ce0 | 2025-03-07T16:57:21.906640+00:00 | EnterPage   |     0 | United States | US           | New Jersey       | NJ               | Clementon
 13 | 5fe640e8-a285-4bcb-8766-5f5be1f96ce0 | 2025-03-07T16:57:26.793640+00:00 | PressButton |     1 | United States | US           | New Jersey       | NJ               | Clementon
 14 | 5fe640e8-a285-4bcb-8766-5f5be1f96ce0 | 2025-03-07T16:57:30.042640+00:00 | PressButton |     2 | United States | US           | New Jersey       | NJ               | Clementon
 15 | 5fe640e8-a285-4bcb-8766-5f5be1f96ce0 | 2025-03-07T16:57:36.491640+00:00 | PressButton |     4 | United States | US           | New Jersey       | NJ               | Clementon
 16 | e1a06fd1-55b9-4928-8820-2e47a664563d | 2025-03-07T16:48:36.313072+00:00 | PressButton |     1 | United States | US           | California       | CA               |
 17 | 4660b366-4a68-490b-b77f-55702c863884 | 2025-03-07T16:56:21.618838+00:00 | EnterPage   |     0 | United States | US           | Wyoming          | WY               | Cheyenne
 18 | 4660b366-4a68-490b-b77f-55702c863884 | 2025-03-07T16:56:23.873838+00:00 | PressButton |     1 | United States | US           | Wyoming          | WY               | Cheyenne
 19 | 4660b366-4a68-490b-b77f-55702c863884 | 2025-03-07T16:56:29.618838+00:00 | PressButton |     4 | United States | US           | Wyoming          | WY               | Cheyenne
 20 | 4660b366-4a68-490b-b77f-55702c863884 | 2025-03-07T16:56:38.781838+00:00 | PressButton |     7 | United States | US           | Wyoming          | WY               | Cheyenne
 21 | 4660b366-4a68-490b-b77f-55702c863884 | 2025-03-07T16:56:43.744838+00:00 | PressButton |     8 | United States | US           | Wyoming          | WY               | Cheyenne
 22 | e1a06fd1-55b9-4928-8820-2e47a664563d | 2025-03-07T16:48:31.863072+00:00 | EnterPage   |     0 | United States | US           | California       | CA               |
 23 | 4660b366-4a68-490b-b77f-55702c863884 | 2025-03-07T16:56:25.308838+00:00 | PressButton |     2 | United States | US           | Wyoming          | WY               | Cheyenne
 24 | 4660b366-4a68-490b-b77f-55702c863884 | 2025-03-07T16:56:32.269838+00:00 | PressButton |     5 | United States | US           | Wyoming          | WY               | Cheyenne
 25 | 5fe640e8-a285-4bcb-8766-5f5be1f96ce0 | 2025-03-07T16:57:32.397640+00:00 | PressButton |     3 | United States | US           | New Jersey       | NJ               | Clementon
 26 | 5fe640e8-a285-4bcb-8766-5f5be1f96ce0 | 2025-03-07T16:57:37.446640+00:00 | PressButton |     5 | United States | US           | New Jersey       | NJ               | Clementon
 27 | 5fe640e8-a285-4bcb-8766-5f5be1f96ce0 | 2025-03-07T16:57:42.441640+00:00 | PressButton |     6 | United States | US           | New Jersey       | NJ               | Clementon
 28 | 5fe640e8-a285-4bcb-8766-5f5be1f96ce0 | 2025-03-07T16:57:43.888640+00:00 | ExitPage    |     7 | United States | US           | New Jersey       | NJ               | Clementon
 29 | 4a80bd19-624f-4475-8cef-0091a042e78f | 2025-03-07T16:59:37.483865+00:00 | EnterPage   |     0 | India         | IN           |                  |                  |
 30 | 4a80bd19-624f-4475-8cef-0091a042e78f | 2025-03-07T16:59:38.089865+00:00 | PressButton |     1 | India         | IN           |                  |                  |
 31 | 4a80bd19-624f-4475-8cef-0091a042e78f | 2025-03-07T16:59:42.719865+00:00 | PressButton |     2 | India         | IN           |                  |                  |
 32 | 4a80bd19-624f-4475-8cef-0091a042e78f | 2025-03-07T16:59:46.774865+00:00 | PressButton |     3 | India         | IN           |                  |                  |
 33 | 4a80bd19-624f-4475-8cef-0091a042e78f | 2025-03-07T16:59:50.051865+00:00 | PressButton |     4 | India         | IN           |                  |                  |
 34 | 4a80bd19-624f-4475-8cef-0091a042e78f | 2025-03-07T16:59:54.094865+00:00 | PressButton |     5 | India         | IN           |                  |                  |
 35 | 4a80bd19-624f-4475-8cef-0091a042e78f | 2025-03-07T16:59:57.012865+00:00 | ExitPage    |     6 | India         | IN           |                  |                  |
(35 rows)
```

## Integrating all of that into the web app

In the main directory:
```
fastapi dev src/app.py
```

(or, for more production-y use, `fastapi run src/app.py`)

...now working on making the app and the script share code...
