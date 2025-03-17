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
        {'name': 'timestamp', 'type': 'string'},
        {'name': 'action', 'type': 'string'},
        {'name': 'cohort, 'type': ['null', 'integer'], 'default': 'null'},
        {'name': 'count', 'type': 'int'},
        {'name': 'country_name', 'type': 'string'},
        {'name': 'country_code', 'type': 'string'},
        {'name': 'subdivision_name', 'type': 'string'},
        {'name': 'subdivision_code', 'type': 'string'},
        {'name': 'city_name', 'type': 'string'},
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
* **cohort** is either `None` (`null`) or a (small) integer. If it's `None`
  then this message was generated by the fake data producer script. Otherwise,
  we can use this number to assign the person clicking to one of a set of
  groups, or cohorts, for some experimental reason.
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

### Cohort

Add `cohort` to the messages. This is an optional integer which can be used to
group participants. If it's `None` / `null` then it means that the data was
generated by the fake data producer.

(The real purpose for adding this is to allow us to identify fake data. And
`None` means that when I add the column to the table, the retroactive data
should be ok.)

```sql
alter table button_presses add column cohort smallint;
```

```sql
defaultdb=> \d button_presses
                             Table "public.button_presses"
      Column      |     Type      | Collation | Nullable |           Default
------------------+---------------+-----------+----------+------------------------------
 id               | bigint        |           | not null | generated always as identity
 session_id       | uuid          |           | not null |
 timestamp        | character(32) |           | not null |
 action           | text          |           | not null |
 count            | bigint        |           | not null |
 country_name     | text          |           | not null |
 country_code     | character(2)  |           | not null |
 subdivision_name | text          |           |          |
 subdivision_code | text          |           |          |
 city_name        | text          |           |          |
 cohort           | smallint      |           |          |
Indexes:
    "button_presses_pkey" PRIMARY KEY, btree (id)
```

> **Note** I've gone back and edited the section describing messages, but not
> earlier SQL results

> **Note** Because I set the JDBC connector to disallow schema evolution, I
> had to restart the connector. 

### More refactoring

The code in [`src/message_support/py`](src/message_support.py) (honestly, not
a great name for the file), which is the code used in the fake message script,
should now be suitable for using in the app, at least to a first
approximation.

### And cookie support

The easiest way to handle "sessions" is to use cookies. Actual sessions are
overkill.

However, that means:

* No way to tell when a user "session" ends, as there's now obvious way to
  tell when the window is closed
* We *can* time the cookie out, and we can refresh it when the user interacts
  with the page
* That also means the `count` field isn't useful any more
* We *can* still produce an event when the user first sets the cookie, which
  should be their first visit to the index page, modulo cookie expiration. Is
  that still worth having?

For the moment, the cookie contents is:
```python
class Cookie(BaseModel):
    session_id: str
    cohort: int | None
    country_name: str
    country_code: str
    subdivision_name: str    # may be ''
    subdivision_code: str    # may be ''
    city_name: str           # may be ''
```

Doing all of this will mean
1. Changing the PG schema, and the Karapace schema
2. Changing how the fake data script works (a little)
3. Doubtless some refactoring around the shared code to make it sensible.

Our PG table will now need to look like:
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

and the `action` enum now only needs to be

```
CREATE TYPE action as ENUM ('EnterPage', 'PressButton');
```


For the existing database, we can leave the enum as it is, and
```
defaultdb=> alter table button_presses drop column count;
```

...and the app now sends Avro encoded messages to Kafka, which in turn end up
in the PG database.

So now to make all of that tidy!

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

# Connecting to ClickHouse

Ideally we use the same JDBC / Avro connector as for PG, so the data stream is
common.

Relevant Aiven docs:

* The generic [Create a JDBC sink connector from Apache Kafka® to another
  database](https://aiven.io/docs/products/kafka/kafka-connect/howto/jdbc-sink)
* But lo [Create a ClickHouse sink connector for Aiven for Apache
  Kafka®](https://aiven.io/docs/products/kafka/kafka-connect/howto/clickhouse-sink-connector)
  uses an integration
* And actually [Connect Apache Kafka® to Aiven for
  ClickHouse®](https://aiven.io/docs/products/clickhouse/howto/integrate-kafka)
  and
  [https://aiven.io/docs/products/clickhouse/reference/supported-input-output-formats](https://aiven.io/docs/products/clickhouse/reference/supported-input-output-formats)
 
  And two of the supported formats are
 
  * Avro: Binary Avro format with embedded schema, as per
    https://avro.apache.org/ - this presumably has the "bigger message"
    problem we wanted to avoid with JSON messages needing to carry a JSON
    schema (although, packed more efficiently)
  * AvroConfluent: Binary Avro with schema registry. Requires the Karapace
    Schema Registry to be enabled in the Kafka service. Which sounds just like
    what we want.

The article [Connecting Apache Kafka® and Aiven for
ClickHouse®](https://aiven.io/developer/connecting-kafka-and-clickhouse) also
looks like it will be useful, and when we want to encapsulate the system in
terraform, [Aiven for Apache Kafka® as a source for Aiven for
ClickHouse®](https://aiven.io/developer/kafka-source-for-clickhouse) will
likely be useful.

## Create our ClickHouse service

```
set -x CH_SERVICE_NAME tibs-button-ch
```

We want the same region as the Kafka service.

What plan? According to [Aiven Plans and Pricing
(ClickHouse)](https://aiven.io/pricing?product=clickhouse&tab=plan-pricing), a
hobbyist plan gives 180GB total storage, and a startup plan gives 1150-4600GB.
For the purposes of this demo, a hobbyist plan would be quite sufficient.
*However* we would like to use an integration to connect Kafka to ClickHouse, and
[Create a ClickHouse sink connector for Aiven for Apache
Kafka®](https://aiven.io/docs/products/kafka/kafka-connect/howto/clickhouse-sink-connector)
points out that "Aiven for ClickHouse service integrations are available for
Startup plans and higher."

In the region we want, the smallest startup plan at the moment is `startup-16`
```
; avn service plans --service-type clickhouse --cloud google-europe-west1
ClickHouse - Fast resource-effective data warehouse for analytical workloads Plans:

    clickhouse:hobbyist            $0.233/h  Hobbyist (1 CPU, 4 GB RAM, 180 GB disk)
    clickhouse:startup-16          $0.685/h  Startup-16 (2 CPU, 16 GB RAM, 1150 GB disk)
    clickhouse:startup-32          $1.370/h  Startup-32 (4 CPU, 32 GB RAM, 2300 GB disk)
    clickhouse:startup-64          $2.740/h  Startup-64 (8 CPU, 64 GB RAM, 4600 GB disk)
    ...
```

So let's do it
```
; avn service create $CH_SERVICE_NAME          \
          --service-type clickhouse            \
          --cloud google-europe-west1          \
          --plan startup-16
```

And we can do the normal
```
; avn service wait $CH_SERVICE_NAME
```

Once that's running, we're going to follow
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

which shows we've got a Kafka to ClickHouse integration running (bit not the
other way round)

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
a bit, I can use
```
; avn service integration-list $CH_SERVICE_NAME --json | jq '. | map(select(.integration_type == "clickhouse_kafka"))[0].service_integration_id'
"ce2f14fb-68c1-46ee-8be2-181b4acf515b"
```
But I don't want the double quotes round the value, so I need to give the `-r` (`--raw-output`)
switch to `jq`
```
; avn service integration-list $CH_SERVICE_NAME --json | jq -r '. | map(select(.integration_type == "clickhouse_kafka"))[0].service_integration_id'
ce2f14fb-68c1-46ee-8be2-181b4acf515b
```
and thus save it as
```
set -x KAFKA_CH_SERVICE_INTEGRATION_ID (avn service integration-list $CH_SERVICE_NAME --json | jq -r '. | map(select(.integration_type == "clickhouse_kafka"))[0].service_integration_id')
```

and to check
```
; echo $KAFKA_CH_SERVICE_INTEGRATION_ID
"ce2f14fb-68c1-46ee-8be2-181b4acf515b"
```

Given that, we can say what we want the integration to do. The example uses
in-line JSON on the command line, but we're going to create a file called
`kafka-ch-integration-config.json` for convenience. It should look like
```json
{
    "tables": [
        {
            "name": "button_presses_from_kafka",
            "columns": [
                {"name": "session_id", "type": "UUID"},
                {"name": "timestamp", "type": "DateTime"},
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

In the above:

* We describe the Kafka messages in the `button_presses_from_kafka` section.
  ClickHouse will write data into an intermediate service table (check the
  terminology) with this name.
* We know the data is in `AvroConfluent` form
* The topic is `button_presses`

We then set the integration configuration
```
avn service integration-update \
    $KAFKA_CH_SERVICE_INTEGRATION_ID \
    --user-config-json @kafka-ch-integration-config.json
```

To see what ClickHouse is doing, I want the ClickHouse CLI.
See [ClickHouse Client](https://clickhouse.com/docs/interfaces/cli) for
options on install it.

There *is* a homebrew option (`brew install --cask clickhouse`), but it's not
mentioned on the ClickHouse web site, so I do what *that* advises
```
; curl https://clickhouse.com/ | sh
```

which puts the `clickhouse` binary in my current directory. Which is good
enough for now (and also installs a more up-to-date version of the command -
25.3.1.1803 versus 25.2.1.3085-stable).

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

and once in
```
tibs-button-ch-1 :) show databases

SHOW DATABASES

Query id: c88dd48a-fbd6-4fda-9ced-4a3807033f6c

   ┌─name──────────────────────┐
1. │ INFORMATION_SCHEMA        │
2. │ default                   │
3. │ information_schema        │
4. │ service_tibs-button-kafka │
5. │ system                    │
   └───────────────────────────┘

5 rows in set. Elapsed: 0.001 sec.
```

```
tibs-button-ch-1 :) show tables from `service_tibs-button-kafka`

SHOW TABLES FROM `service_tibs-button-kafka`

Query id: 2d17d7f0-063c-4c0e-b5b9-eb9a921dcd56

   ┌─name──────────────────────┐
1. │ button_presses_from_kafka │
   └───────────────────────────┘

1 row in set. Elapsed: 0.002 sec.
```

```
tibs-button-ch-1 :) describe `service_tibs-button-kafka`.button_presses_from_kafka

DESCRIBE TABLE `service_tibs-button-kafka`.button_presses_from_kafka

Query id: a11d173b-add0-44bc-87d7-9669ee65bcf5

   ┌─name─────────────┬─type────────────┬─default_type─┬─default_expression─┬─comment─┬─codec_expression─┬─ttl_expression─┐
1. │ session_id       │ UUID            │              │                    │         │                  │                │
2. │ timestamp        │ DateTime        │              │                    │         │                  │                │
3. │ action           │ String          │              │                    │         │                  │                │
4. │ country_name     │ String          │              │                    │         │                  │                │
5. │ country_code     │ FixedString(2)  │              │                    │         │                  │                │
6. │ subdivision_name │ String          │              │                    │         │                  │                │
7. │ subdivision_code │ String          │              │                    │         │                  │                │
8. │ city_name        │ String          │              │                    │         │                  │                │
9. │ cohort           │ Nullable(Int16) │              │                    │         │                  │                │
   └──────────────────┴─────────────────┴──────────────┴────────────────────┴─────────┴──────────────────┴────────────────┘

9 rows in set. Elapsed: 0.001 sec.
```

We *can* look at the messages in this table, but that will "eat" them.

Following the tutorial, we need to create somewhere for the data to go -
section [Persist Kafka messages in Clickhouse
table](https://aiven.io/developer/connecting-kafka-and-clickhouse#persist-kafka-messages-in-clickhouse-table)

We need a destination table, where the data will get stored permanently, and a
materialised view, to act as the bridge from the service table to that
destination table.

```
CREATE TABLE button_presses (
                session_id UUID,
                timestamp DateTime,
                action String,
                country_name String,
                country_code FixedString(2),
                subdivision_name String,
                subdivision_code String,
                city_name String,
                cohort Nullable(Smallint)

)
ENGINE = ReplicatedMergeTree()
ORDER BY timestamp
```

which looks like:
```
tibs-button-ch-1 :) CREATE TABLE button_presses (
                session_id UUID,
                timestamp DateTime,
                action String,
                country_name String,
                country_code FixedString(2),
                subdivision_name String,
                subdivision_code String,
                city_name String,
                cohort Nullable(Smallint)

)
ENGINE = ReplicatedMergeTree()
ORDER BY timestamp


CREATE TABLE button_presses
(
    `session_id` UUID,
    `timestamp` DateTime,
    `action` String,
    `country_name` String,
    `country_code` FixedString(2),
    `subdivision_name` String,
    `subdivision_code` String,
    `city_name` String,
    `cohort` Nullable(Smallint)
)
ENGINE = ReplicatedMergeTree
ORDER BY timestamp

Query id: 25e4561b-338d-43ab-8038-936629ba32b6

   ┌─shard───┬─replica──────────────────────────────────┬─status─┬─num_hosts_remaining─┬─num_hosts_active─┐
1. │ s_4c27c │ tibs-button-ch-1.devrel-tibs.aiven.local │ OK     │                   0 │                0 │
   └─────────┴──────────────────────────────────────────┴────────┴─────────────────────┴──────────────────┘

1 row in set. Elapsed: 0.047 sec.
```

and then
```
CREATE MATERIALIZED VIEW materialised_view TO button_presses AS
SELECT * FROM `service_tibs-button-kafka`.button_presses_from_kafka;
```

which looks like
```
tibs-button-ch-1 :) CREATE MATERIALIZED VIEW materialised_view TO button_presses AS
SELECT * FROM `service_tibs-button-kafka`.button_presses_from_kafka;


CREATE MATERIALIZED VIEW materialised_view TO button_presses
AS SELECT *
FROM `service_tibs-button-kafka`.button_presses_from_kafka

Query id: fadbec2c-af73-44c6-88df-573b8ec77e8f

   ┌─shard───┬─replica──────────────────────────────────┬─status─┬─num_hosts_remaining─┬─num_hosts_active─┐
1. │ s_4c27c │ tibs-button-ch-1.devrel-tibs.aiven.local │ OK     │                   0 │                0 │
   └─────────┴──────────────────────────────────────────┴────────┴─────────────────────┴──────────────────┘

1 row in set. Elapsed: 0.013 sec.
```

Unfortunately, data doesn't seem to be coming through.


The missing piece may be telling ClickHouse about the schema repository
(unsurprisingly). It looks as if the ClickHouse page
[AvroConfluent](https://clickhouse.com/docs/interfaces/formats/AvroConfluent)
may be my friend...

For debugging purposes, try the following at the ClickHouse SQL prompt:

```
SET format_avro_schema_registry_url = 'https://avnadmin:<password>@tibs-button-kafka-devrel-tibs.l.aivencloud.com:10148'
```

and send some more data...

...but still no joy

Let's check the support datatypes for AvroConfluent, as documented at
[AvroConfluent](https://clickhouse.com/docs/interfaces/formats/AvroConfluent)

The two problems may be the `string` -> `UUID`, and the `string` -> `datetime`

[`data_time_input_format`](https://clickhouse.com/docs/operations/settings/formats#date_time_input_format)
says that the "Cloud default value" is `best_effort`, which should understand
the ISO 8601 strings I'm sending.

**But**
```
tibs-button-ch-1 :) select name, value from system.settings where name = 'date_time_input_format'

SELECT
    name,
    value
FROM system.settings
WHERE name = 'date_time_input_format'

Query id: 3d7db67e-57ce-4725-a3a1-e3dcac768d3d

   ┌─name───────────────────┬─value─┐
1. │ date_time_input_format │ basic │
   └────────────────────────┴───────┘

1 row in set. Elapsed: 0.003 sec. Processed 1.09 thousand rows, 241.21 KB (392.62 thousand rows/s., 86.49 MB/s.)
Peak memory usage: 0.00 B.
```
and `basic` doesn't understand the `T` in the string or the timezone
information.

```
tibs-button-ch-1 :) set date_time_input_format = 'best_effort'

SET date_time_input_format = 'best_effort'

Query id: 0a90e346-a51b-403e-a746-faca7c69de41

Ok.

0 rows in set. Elapsed: 0.049 sec.
```

Hmm. Looking at the logs (in the console) it is saying
```
[tibs-button-ch-1]2025-03-12T15:48:32.797461[clickhouse]2025.03.12 15:48:32.797379 [ 708 ] {} <Error> StorageKafka (button_presses_from_kafka): void DB::StorageKafka::threadFunc(size_t) Code: 44. DB::Exception: Type DateTime is not compatible with Avro string:
```

so maybe I should give up and use an integer timestamp in my Avro messages.

> Meanwhile, let's stop the service integration:
>
> `; avn service integration-delete  $KAFKA_CH_SERVICE_INTEGRATION_ID`

According to the AvroConfluent docs, `long (timestamp-millis)` and `long
(timestamp-micros)` *will* convert to a `DateTime64`.

Ah! There's a section I'd missed in the [Avro
spec](https://avro.apache.org/docs/1.11.1/specification/) (as an excuse, it is
at the end) on **Logical Types**, including
* `uuid` - this annotates a string
* `timestamp-millis` - this annotates a long
* `timestamp-micros` - this annotates a long

For instance:
```json
{ "type": "string", "logicalType": "uuid" }
```

So my Avro schema would ideally be 

## Avro schema refinement

The old Avro schema looked like (I'm just showing the column definitions, not
the whole thing, and this is actually Python code, since that's where we
definte the schema - run with it :))
```
[
    {'name': 'session_id', 'type': 'string'},
    {'name': 'timestamp', 'type': 'string'},
    {'name': 'action', 'type': 'string'},
    {'name': 'country_name', 'type': 'string'},
    {'name': 'country_code', 'type': 'string'},
    {'name': 'subdivision_name', 'type': 'string'},
    {'name': 'subdivision_code', 'type': 'string'},
    {'name': 'city_name', 'type': 'string'},
    {'name': 'cohort', 'type': ['null', 'int'], 'default': 'null'},
]
```

It *sounds* as if we actually want
```
[
    {'name': 'session_id', 'type': 'string', 'logicalType': 'uuid'},
    {'name': 'timestamp', 'type': 'long', 'logicalType': 'timestamp_micros},
    {'name': 'action', 'type': 'string'},
    {'name': 'country_name', 'type': 'string'},
    {'name': 'country_code', 'type': 'string'},
    {'name': 'subdivision_name', 'type': 'string'},
    {'name': 'subdivision_code', 'type': 'string'},
    {'name': 'city_name', 'type': 'string'},
]
```

That doesn't require a change in the Python code for the `session_id` (it's
still a string), but it *does* mean a change for the `timestamp`.

What resolution should we use?

Python's `datetime.datetime.now().timestamp()` gives a floating point value
representing seconds, but the resolution appears to be microseconds, so one
can do
```
now_utc = datetime.datetime.now(datetime.timezone.utc)
microseconds_since_epoch = int(now_utc.timestamp() * 1000_000)
```

The Postgres documentation confirms that its `timestamp with time zone`
resolves to the microsecond, but ([Time
Stamps](https://www.postgresql.org/docs/current/datatype-datetime.html#DATATYPE-DATETIME-INPUT-TIME-STAMPS))
it looks as if it will only take a string as input. So it *may* be
best/simplest just to use a `bigint` (an 8 byte integer)

What about the datatypes supported by the JDBC connector? The tables in the
Aiven Open [kafka Connect JDBC Sink
Connector](https://github.com/Aiven-Open/jdbc-connector-for-apache-kafka/blob/master/docs/sink-connector.md)
docs appear to suggest that "Connect schema type" `Timestamp` converts to PG
`TIMESTAMP`

Hmm. In my PG table, `timestamp` was a `character(32)`.

Let's change to a `timestamptz` (the lazy way):

```
defaultdb=> alter table button_presses drop column timestamp;
defaultdb=> alter table button_presses add column timestamp timestamptz;
```
and it's now a `timestamp with time zone`.

And as expected, the conncetor logs an error:
```
ERROR: column "timestamp" is of type timestamp with time zone but expression is of type bigint
  Hint: You will need to rewrite or cast the expression.
```

which I might be able to fix by Postgres magic, but it's simpler just to use a bigint...

So, let's do that
```
defaultdb=> alter table button_presses drop column timestamp;
defaultdb=> alter table button_presses add column timestamp bigint;
```

and delete / create the connector, and send data again ... and now I can see
the integer timestamps. So let's live with that, at least for now.

Let's restart the ClickHouse integration

```
; avn service integration-create            \
          --integration-type clickhouse_kafka   \
          --source-service $KAFKA_SERVICE_NAME\
      --dest-service $CH_SERVICE_NAME
```

```
set -x KAFKA_CH_SERVICE_INTEGRATION_ID (avn service integration-list $CH_SERVICE_NAME --json | jq -r '. | map(select(.integration_type == "clickhouse_kafka"))[0].service_integration_id')
```

```
avn service integration-update \
    $KAFKA_CH_SERVICE_INTEGRATION_ID \
    --user-config-json @kafka-ch-integration-config.json
```

Back in ClickHouse:

1. Still getting errors in the log
2. I've realised I should have made the column datatype `DateTime('UTC')`

Fixing that second, first:
```json
  1 {
  2     "tables": [
  3         {
  4             "name": "button_presses_from_kafka",
  5             "columns": [
  6                 {"name": "session_id", "type": "UUID"},
  7                 {"name": "timestamp", "type": "DateTime('UTC')"},
  8                 {"name": "action", "type": "String"},
  9                 {"name": "country_name", "type": "String"},
 10                 {"name": "country_code", "type": "FixedString(2)"},
 11                 {"name": "subdivision_name", "type": "String"},
 12                 {"name": "subdivision_code", "type": "String"},
 13                 {"name": "city_name", "type": "String"},
 14                 {"name": "cohort", "type": "Nullable(Smallint)"}
 15             ],
 16             "topics": [{"name": "button_presses"}],
 17             "data_format": "AvroConfluent",
 18             "group_name": "button_presses_from_kafka_consumer"
 19         }
 20     ]
 21 }
```

and update the integration
```
; avn service integration-update \
          $KAFKA_CH_SERVICE_INTEGRATION_ID \
          --user-config-json @kafka-ch-integration-config.json
```

After that,
```
describe `service_tibs-button-kafka`.button_presses_from_kafka
```
shows the `timestamp` column as being `DateTime('UTC')`

```
tibs-button-ch-1 :) drop table materialised_view
DROP TABLE button_presses
```

and try recreating them
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

```
CREATE MATERIALIZED VIEW materialised_view TO button_presses AS
SELECT * FROM `service_tibs-button-kafka`.button_presses_from_kafka;

```

Hmm. I'm still getting
```
[tibs-button-ch-1]2025-03-12T18:41:23.147343[clickhouse]2025.03.12 18:41:23.147269 [ 681 ] {} <Error> StorageKafka (button_presses_from_kafka): void DB::StorageKafka::threadFunc(size_t) Code: 44. DB::Exception: Type DateTime('UTC') is not compatible with Avro string:
```
in the logs.


??? Is it old messages ???

Let's delete and recreate the topic

1. Disconnect from CH
2. Delete the connector

(I used the console for convenience)


```
; avn service topic-delete $KAFKA_SERVICE_NAME $KAFKA_BUTTON_TOPIC
```

```
; avn service topic-create      \
      --partitions 3            \
      --replication 2           \
      --remote-storage-enable   \
      --local-retention-ms 5000 \
      $KAFKA_SERVICE_NAME $KAFKA_BUTTON_TOPIC
```

and restart/reconnect things

```
; avn service connector create $KAFKA_SERVICE_NAME @pg_avro_sink.json
```

```
; avn service integration-create            \
          --integration-type clickhouse_kafka   \
          --source-service $KAFKA_SERVICE_NAME\
      --dest-service $CH_SERVICE_NAME
```

```
set -x KAFKA_CH_SERVICE_INTEGRATION_ID (avn service integration-list $CH_SERVICE_NAME --json | jq -r '. | map(select(.integration_type == "clickhouse_kafka"))[0].service_integration_id')
```

```
avn service integration-update \
    $KAFKA_CH_SERVICE_INTEGRATION_ID \
    --user-config-json @kafka-ch-integration-config.json
```

and generate some new data.

Which shows up in PG.

And now in the CH logs I have
```
[tibs-button-ch-1]2025-03-12T19:00:24.366561[clickhouse]2025.03.12 19:00:24.366488 [ 723 ] {} <Error> StorageKafka (button_presses_from_kafka): void DB::StorageKafka::threadFunc(size_t) Code: 117. DB::Exception: Unexpected type for default value: Expected null, but found string in line 1: while fetching schema id = 6: (at row 1)
```

Schema id `6` matches what the data generator said it used.

Let's look:

```
; curl -X GET https://avnadmin:<password>@tibs-button-kafka-devrel-tibs.l.aivencloud.com:10148/schemas/ids/6
{"schema":"{\"doc\":\"Web app interactions\",\"fields\":[{\"logicalType\":\"uuid\",\"name\":\"session_id\",\"type\":\"string\"},{\"logicalType\":\"timestamp-millis\",\"name\":\"timestamp\",\"type\":\"long\"},{\"name\":\"action\",\"type\":\"string\"},{\"name\":\"country_name\",\"type\":\"string\"},{\"name\":\"country_code\",\"type\":\"string\"},{\"name\":\"subdivision_name\",\"type\":\"string\"},{\"name\":\"subdivision_code\",\"type\":\"string\"},{\"name\":\"city_name\",\"type\":\"string\"},{\"default\":\"null\",\"name\":\"cohort\",\"type\":[\"null\",\"int\"]}],\"name\":\"button_presses\",\"type\":\"record\"}"}⏎
```

or using `jq` (twice!)

```
; curl -X GET https://avnadmin:<password>@tibs-button-kafka-devrel-tibs.l.aivencloud.com:10148/schemas/ids/6 | jq -r .schema | jq
{
  "doc": "Web app interactions",
  "fields": [
    {
      "logicalType": "uuid",
      "name": "session_id",
      "type": "string"
    },
    {
      "logicalType": "timestamp-millis",
      "name": "timestamp",
      "type": "long"
    },
    {
      "name": "action",
      "type": "string"
    },
    {
      "name": "country_name",
      "type": "string"
    },
    {
      "name": "country_code",
      "type": "string"
    },
    {
      "name": "subdivision_name",
      "type": "string"
    },
    {
      "name": "subdivision_code",
      "type": "string"
    },
    {
      "name": "city_name",
      "type": "string"
    },
    {
      "default": "null",
      "name": "cohort",
      "type": [
        "null",
        "int"
      ]
    }
  ],
  "name": "button_presses",
  "type": "record"
}
```

-----

Next day, looking at it afresh...

* error message `Unexpected type for default value: Expected null, but found string`
* line in Avro schema definition
  ```python
  {'name': 'cohort', 'type': ['null', 'int'], 'default': 'null'},
  ```
* but that's a Python code, so it should be
  ```python
  {'name': 'cohort', 'type': ['null', 'int'], 'default': None},
  ```
  
Changing that causes the schema id to go up to 7 (good) when I send fake data.

I'm still getting errors about schema id 6 in the ClickHouse log, presumably
because it's trying to read old messages.

Let's "restart" the topic again (as we did earlier)

**And now I see  the data in ClickHouse!**

From the data generator
```
EVENT session_id='67b922f3-674c-4542-92f3-d20a75a55ea9' timestamp=1741859682470739 cohort=0 action='EnterPage' country_name='United States' country_code='US' subdivision_name='' subdivision_code='' city_name=''
EVENT session_id='67b922f3-674c-4542-92f3-d20a75a55ea9' timestamp=1741859684450739 cohort=0 action='PressButton' country_name='United States' country_code='US' subdivision_name='' subdivision_code='' city_name=''
EVENT session_id='67b922f3-674c-4542-92f3-d20a75a55ea9' timestamp=1741859685336739 cohort=0 action='PressButton' country_name='United States' country_code='US' subdivision_name='' subdivision_code='' city_name=''
```

and in ClickHouse
```
tibs-button-ch-1 :) select * from button_presses

SELECT *
FROM button_presses

Query id: 82100a27-c8a1-4934-a969-7bb3a90dcc93

   ┌─session_id───────────────────────────┬───────────timestamp─┬─action──────┬─country_name──┬─country_code─┬─subdivision_name─┬─subdivision_code─┬─city_name─┬─cohort─┐
1. │ 67b922f3-674c-4542-92f3-d20a75a55ea9 │ 2012-05-01 02:32:51 │ EnterPage   │ United States │ US           │                  │                  │           │      0 │
2. │ 67b922f3-674c-4542-92f3-d20a75a55ea9 │ 2012-05-24 00:32:51 │ PressButton │ United States │ US           │                  │                  │           │      0 │
3. │ 67b922f3-674c-4542-92f3-d20a75a55ea9 │ 2012-06-03 06:39:31 │ PressButton │ United States │ US           │                  │                  │           │      0 │
   └──────────────────────────────────────┴─────────────────────┴─────────────┴───────────────┴──────────────┴──────────────────┴──────────────────┴───────────┴────────┘

3 rows in set. Elapsed: 0.003 sec.
```

The only problem now is those timestamps.

For instance, in PG I (from button presses) the sequence

* 1741860319162807
* 1741860322762046
* 1741860323560839
* 1741860324045622

but in ClickHouse I see

* 2032-07-04 05:27:19
* 2032-08-14 21:14:38
* 2032-08-24 03:07:51
* 2032-08-29 17:47:34

(not necessarily in the same order, but with the same session id, and the
first one *is* the first one because it's a PageEntry event).

https://clickhouse.com/docs/sql-reference/data-types/datetime indicates that
we *can* input a DateTime as an integer, and that `DateTime('UTC')` should
indicate that it's in that timezone.

Both the service table and the button presses table have the column with that type.

https://clickhouse.com/docs/interfaces/formats/AvroConfluent shows that Avro
schema `long (timestamp-micros)` should become the ClickHouse data type
`DateTime64(6)`. The `6` is presumably meant to indicate that there are 6
digits of fractional time (so `microseconds`). But the DateTime documentation
doesn't mention that usage - it only shows the timezone as a parameter for `DateTime`.

So **maybe** the time being used as `DateTime('UTC')` is the problem, and it
should be specified as `DateTime64(6)`.


-----

Hmm. If I go to my Kafka service in the console, and go to the Connectors tab,
and choose a ClickHouse connector, and then choose `Key converter class` as
`io.confluent.connect.avro.AvroConverter` then I get fields in which I can put
the schema information.

**Presumably** I should be able to do this via the command line as well...

...oh, as part of `CREATE TABLE` for the service table.

Let's make a clean slate - stop the ClickHouse integration and destroy various
tables I have in ClickHouse, then restart and recreate stuff.

* Stop the integration using the console.
* `drop table materialised_view`
* `drop table button_presses`
* Because we've stopped the integration, the database
  `service_tibs-button-kafka` has gone away (it's no longer in `show databases`)
  
Change the line in kafka-ch-integration-config.json to use the correct
data/time format:
```json
{
    "tables": [
        {
            "name": "button_presses_from_kafka",
            "columns": [
                {"name": "session_id", "type": "UUID"},
                {"name": "timestamp", "type": "DateTime('UTC')"},
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

Create and update the integration, as before
```
avn service integration-create            \
    --integration-type clickhouse_kafka   \
    --source-service $KAFKA_SERVICE_NAME\
    --dest-service $CH_SERVICE_NAME
```

```
set -x KAFKA_CH_SERVICE_INTEGRATION_ID (avn service integration-list $CH_SERVICE_NAME --json | jq -r '. | map(select(.integration_type == "clickhouse_kafka"))[0].service_integration_id')
```

Now `show databases` shows the service database
```
tibs-button-ch-1 :) show databases

SHOW DATABASES

Query id: 4a20ffad-4dc4-41bf-b6ba-ac152436fc8f

Connecting to tibs-button-ch-devrel-tibs.b.aivencloud.com:10143 as user avnadmin.
Connected to ClickHouse server version 24.8.13.

ClickHouse server version is older than ClickHouse client. It may indicate that the server is out of date and can be upgraded.

   ┌─name──────────────────────┐
1. │ INFORMATION_SCHEMA        │
2. │ default                   │
3. │ information_schema        │
4. │ service_tibs-button-kafka │
5. │ system                    │
   └───────────────────────────┘

5 rows in set. Elapsed: 0.001 sec.
```

```
avn service integration-update \
    $KAFKA_CH_SERVICE_INTEGRATION_ID \
    --user-config-json @kafka-ch-integration-config.json
```

```
tibs-button-ch-1 :) show tables from `service_tibs-button-kafka`

SHOW TABLES FROM `service_tibs-button-kafka`

Query id: b8eeb8f7-dfe8-4a18-8938-28f8abcde1b5

   ┌─name──────────────────────┐
1. │ button_presses_from_kafka │
   └───────────────────────────┘

1 row in set. Elapsed: 0.002 sec.

tibs-button-ch-1 :) describe `service_tibs-button-kafka`.button_presses_from_kafka

DESCRIBE TABLE `service_tibs-button-kafka`.button_presses_from_kafka

Query id: 6f5424fa-beef-42dc-aa40-0062327903ff

   ┌─name─────────────┬─type────────────┬─default_type─┬─default_expression─┬─comment─┬─codec_expression─┬─ttl_expression─┐
1. │ session_id       │ UUID            │              │                    │         │                  │                │
2. │ timestamp        │ DateTime64(6)   │              │                    │         │                  │                │
3. │ action           │ String          │              │                    │         │                  │                │
4. │ country_name     │ String          │              │                    │         │                  │                │
5. │ country_code     │ FixedString(2)  │              │                    │         │                  │                │
6. │ subdivision_name │ String          │              │                    │         │                  │                │
7. │ subdivision_code │ String          │              │                    │         │                  │                │
8. │ city_name        │ String          │              │                    │         │                  │                │
9. │ cohort           │ Nullable(Int16) │              │                    │         │                  │                │
   └──────────────────┴─────────────────┴──────────────┴────────────────────┴─────────┴──────────────────┴────────────────┘

9 rows in set. Elapsed: 0.001 sec.
```

And check if that's worked - ask the service table for its contents (which
will "eat up the entries", but that's OK)

[and remember to send some data with the data creator!]

```
tibs-button-ch-1 :) select * from `service_tibs-button-kafka`.button_presses_from_kafka

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

and yes, there it is.

Note that:
1. I believe the Karapace schema location is set up for us by the integration,
   but I can double check that later on by deleting the ClickHouse service and
   recreating everything.
2. The timestamps are plausible, and are displayed in a friendly form, even
   though stored as integers.

So now to create the actual table we want - let's try
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
staying with an explicit UTC timestamp declaration

and then join things up again
```
CREATE MATERIALIZED VIEW materialised_view TO button_presses AS
SELECT * FROM `service_tibs-button-kafka`.button_presses_from_kafka;
```

Send some more data, and then
```
tibs-button-ch-1 :) select * from button_presses

SELECT *
FROM button_presses

Query id: 8ed97cff-7dae-4bbd-a979-373bd6cbb586

    ┌─session_id───────────────────────────┬───────────timestamp─┬─action──────┬─country_name─┬─country_code─┬─subdivision_name─┬─subdivision_code─┬─city_name─┬─cohort─┐
 1. │ 8b6f3882-7d99-4782-9731-82d411ec7ecf │ 2025-03-13 15:23:13 │ EnterPage   │ China        │ CN           │                  │                  │           │   ᴺᵁᴸᴸ │
 2. │ 8b6f3882-7d99-4782-9731-82d411ec7ecf │ 2025-03-13 15:23:17 │ PressButton │ China        │ CN           │                  │                  │           │   ᴺᵁᴸᴸ │
 3. │ 8b6f3882-7d99-4782-9731-82d411ec7ecf │ 2025-03-13 15:23:19 │ PressButton │ China        │ CN           │                  │                  │           │   ᴺᵁᴸᴸ │
 4. │ 8b6f3882-7d99-4782-9731-82d411ec7ecf │ 2025-03-13 15:23:23 │ PressButton │ China        │ CN           │                  │                  │           │   ᴺᵁᴸᴸ │
 5. │ 53ab8d41-8744-4440-8096-51b4c3f417a2 │ 2025-03-13 15:28:39 │ EnterPage   │ France       │ FR           │                  │                  │           │   ᴺᵁᴸᴸ │
 6. │ 53ab8d41-8744-4440-8096-51b4c3f417a2 │ 2025-03-13 15:28:42 │ PressButton │ France       │ FR           │                  │                  │           │   ᴺᵁᴸᴸ │
 7. │ 53ab8d41-8744-4440-8096-51b4c3f417a2 │ 2025-03-13 15:28:44 │ PressButton │ France       │ FR           │                  │                  │           │   ᴺᵁᴸᴸ │
 8. │ 53ab8d41-8744-4440-8096-51b4c3f417a2 │ 2025-03-13 15:28:47 │ PressButton │ France       │ FR           │                  │                  │           │   ᴺᵁᴸᴸ │
 9. │ 53ab8d41-8744-4440-8096-51b4c3f417a2 │ 2025-03-13 15:28:52 │ PressButton │ France       │ FR           │                  │                  │           │   ᴺᵁᴸᴸ │
10. │ 53ab8d41-8744-4440-8096-51b4c3f417a2 │ 2025-03-13 15:28:53 │ PressButton │ France       │ FR           │                  │                  │           │   ᴺᵁᴸᴸ │
11. │ 53ab8d41-8744-4440-8096-51b4c3f417a2 │ 2025-03-13 15:28:56 │ PressButton │ France       │ FR           │                  │                  │           │   ᴺᵁᴸᴸ │
12. │ 53ab8d41-8744-4440-8096-51b4c3f417a2 │ 2025-03-13 15:28:59 │ PressButton │ France       │ FR           │                  │                  │           │   ᴺᵁᴸᴸ │
13. │ 53ab8d41-8744-4440-8096-51b4c3f417a2 │ 2025-03-13 15:29:03 │ PressButton │ France       │ FR           │                  │                  │           │   ᴺᵁᴸᴸ │
14. │ 53ab8d41-8744-4440-8096-51b4c3f417a2 │ 2025-03-13 15:29:05 │ PressButton │ France       │ FR           │                  │                  │           │   ᴺᵁᴸᴸ │
15. │ 53ab8d41-8744-4440-8096-51b4c3f417a2 │ 2025-03-13 15:29:10 │ PressButton │ France       │ FR           │                  │                  │           │   ᴺᵁᴸᴸ │
    └──────────────────────────────────────┴─────────────────────┴─────────────┴──────────────┴──────────────┴──────────────────┴──────────────────┴───────────┴────────┘

15 rows in set. Elapsed: 0.003 sec.
```

and there's some nice looking data (and hmm, that earlier data doesn't seem to
have been lost).

So, we have end-to-end data (and it's still going to PG as well)

Next thing to do is to delete and recreate the ClickHouse service and
associated things, just to make sure.

So ... stop the integration with Kafka, and delete the service

# Setting up ClickHouse from scratch

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

```
; avn service create $CH_SERVICE_NAME          \
          --service-type clickhouse            \
          --cloud google-europe-west1          \
          --plan startup-16
```

```
; avn service wait $CH_SERVICE_NAME
```

```
avn service integration-create            \
    --integration-type clickhouse_kafka   \
    --source-service $KAFKA_SERVICE_NAME\
    --dest-service $CH_SERVICE_NAME
```

```
set -x KAFKA_CH_SERVICE_INTEGRATION_ID (avn service integration-list $CH_SERVICE_NAME --json | jq -r '. | map(select(.integration_type == "clickhouse_kafka"))[0].service_integration_id')
```

`kafka-ch-integration-config.json` is
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

```
avn service integration-update \
    $KAFKA_CH_SERVICE_INTEGRATION_ID \
    --user-config-json @kafka-ch-integration-config.json
```

Generate some fake data.

```
./clickhouse client \
    --host <HOST> --port <PORT> \
    --user avnadmin --password <PASSWORD> \
    --secure
```

and
```
select * from `service_tibs-button-kafka`.button_presses_from_kafka
```

and after a bit, there's my data!

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

```
CREATE MATERIALIZED VIEW materialised_view TO button_presses AS
SELECT * FROM `service_tibs-button-kafka`.button_presses_from_kafka;
```

```
select * from button_presses
```

which outputs
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

So all seems good.

## Some useful links

Some links on PostgreSQL would probably be good, but honestly the actual
documentation is excellent.

Also some links on the JDBC connector and writing to PG.

[Karapace](https://www.karapace.io/)

ClickHouse documentation [Using Materialized Views in
ClickHouse](https://clickhouse.com/blog/using-materialized-views-in-clickhouse)

ClickHouse on [Creating Tables in
ClickHouse](https://clickhouse.com/docs/guides/creating-tables) which is
useful for its explanation of their interpretation of Primary Keys.
Note that our table could probably be better designed.

[Apache Avro specification](https://avro.apache.org/docs/1.11.1/specification)

ClickHouse on
[AvroConfluent](https://clickhouse.com/docs/interfaces/formats/AvroConfluent)
messages

ClickHouse SQL reference on
[DateTime](https://clickhouse.com/docs/sql-reference/data-types/datetime) and
[DateTime64](https://clickhouse.com/docs/sql-reference/data-types/datetime64)

> **Note** I only just found that last, and it's now clear I can actually
> specify `DateTime64(6, 'UTC')` which is probably what I wanted.

Aiven's documentation on the formats available for messages in the
Kafka/ClickHouse integration [Formats for Aiven for ClickHouse® - Aiven for Apache Kafka® data exchange
](https://aiven.io/docs/products/clickhouse/reference/supported-input-output-formats)

Aiven's documentation on [Connect Apache Kafka® to Aiven for ClickHouse®](https://aiven.io/docs/products/clickhouse/howto/integrate-kafka)

[Get things done with the Aiven CLI](https://aiven.io/developer/aiven-cmdline)
(with PostgreSQL examples)

Aiven articles on Kafka -> ClickHouse - need to clarify which is best for what
* [Stream data from Apache Kafka® to ClickHouse® for real-time
  analytics](https://aiven.io/developer/stream-data-from-apache-kafkar-to-clickhouser-for-real-time-analytics)
* [Aiven for Apache Kafka® as a source for Aiven for
  ClickHouse®](https://aiven.io/developer/kafka-source-for-clickhouse) shows
  how to use Terraform for setting things up
* [Connecting Apache Kafka® and Aiven for
  ClickHouse®](https://aiven.io/developer/connecting-kafka-and-clickhouse#persist-kafka-messages-in-clickhouse-table)
  is the article we took some guidance from, although it uses JSON messages.

## Consumer script


`src/simple_consumer.py` is a consumer that will read and report on events.

## Plans for the other webpages


1. A page showing analysis from ClickHouse - for instance (MVP):

    * Time this session started
    * Number of presses in this session
    * Number of presses from the same:
    
        * Country
        * Subdivision (if we have one)
        * City (if we have one)

2. A page showing output from a Kafka consumer

   How much can it show? Keep it simple.

## Which Python ClickHouse package?

Sensible candidates (that have recent maintenance history) appear to be

* [ClickHouse Connect](https://clickhouse.com/docs/integrations/python), as
  described on the ClickHouse website. This would presumably be the "obvious"
  default to use. It claims to be in Beta. It's [on github](https://github.com/ClickHouse/clickhouse-connect)
 
  In the section [Multithreaded, Multiprocess, and Async/Event Driven Use
  Cases](https://clickhouse.com/docs/integrations/python#multithreaded-multiprocess-and-asyncevent-driven-use-cases)
  it says "ClickHouse Connect works well in multi-threaded, multiprocess, and
  event loop driven/asynchronous applications." and then gives an `awync`
  example at [AsyncClient wrapper](https://clickhouse.com/docs/integrations/python#asyncclient-wrapper)
 
* [clickhouse-driver](https://clickhouse-driver.readthedocs.io/en/latest/index.html)
  ([github](https://github.com/mymarilyn/clickhouse-driver)) appears to be
  what the Aiven documentation suggests. However, as it says at [Async and
  multithreading](https://clickhouse-driver.readthedocs.io/en/latest/quickstart.html#async-and-multithreading)
  it doesn't help with asynchronous use.
 
  There is an asynchronous wrapper at
  [aioch](https://github.com/mymarilyn/aioch) but that doesn't appear to have
  had a commit for 3 years.
 
* [asynch](https://github.com/long2ice/asynch) looks interesting - it says it
  "reuses most of clickhouse-driver features" and "complies with
  [PEP-249(https://www.python.org/dev/peps/pep-0249/)]" (the Python Database
  API Specification v2.0).
 
* [aiochclient](https://github.com/maximdanilchenko/aiochclient) also looks
  interesting, and has explicit support for `aiohttp` and `httpx`

In the end, for the moment, I think that `clickhouse-connect` looks like the
sensible place to start

## Adding a `/stats` page to the app

We need the ClickHouse service connection data.

> **Note** that `clickhouse-connect` talks over HTTPS, not the wire protocol,
> so it wants the HTTPS port, which we can see with
> ```
> ; avn service get $CH_SERVICE_NAME --json | jq '.components | map(select(.component == "clickhouse_https"))'
> ```

So, remembering the `-r` to remove any extraneous quoting:
```
; set CH_HOST (avn service get $CH_SERVICE_NAME --json | jq -r '.components | map(select(.component == "clickhouse_https"))[0].host')
```

The username and password are simpler :)
```
; set -x CH_USERNAME (avn service get $CH_SERVICE_NAME --json | jq -r '.service_uri_params.user')
; set -x CH_PASSWORD (avn service get $CH_SERVICE_NAME --json | jq -r '.service_uri_params.password')
```

Unfortunately, trying to connect (with either `get_client` or
`get_async_client`) gives me an error:
```
urllib3.exceptions.ProtocolError: ('Connection aborted.', ConnectionResetError(54, 'Connection reset by peer'))
```
and further down the stack
```
clickhouse_connect.driver.exceptions.OperationalError: Error ('Connection aborted.', ConnectionResetError(54, 'Connection reset by peer')) executing HTTP request attempt 2 (http://tibs-button-ch-devrel-tibs.b.aivencloud.com:10144)
```
(and that's whether I use the HTTPS or native port). And *of course* I don't
expect an `http://` connection to work for an Aiven service :(

So let's try a different library...

...let's try `asynch`, as it advertises as like clickhouse-driver, which
is/was the other main ClickHouse Python library.

The connect callable will take a full URI (with password, etc.) or the
parts we defined already, so since we've got those, let's use them.

Unfortunately, now I get
```
asynch.errors.UnexpectedPacketFromServerError: Code: 102. Unexpected packet from server tibs-button-ch-devrel-tibs.b.aivencloud.com:10144 (expected Hello or Exception, got Unknown packet)
```
(and yes, I get the same if I use port 10143, even though that's not the port
I would expect)

---

Trying the other other client
```
; pip install aiochclient[httpx]
```

...and at least with this one I can get a response back!

So I can get nice reporting back, but I still need to:

1. Adjust the environment variables to have a SERVICE_URI instead of HOST and
   PORT
2. Move the creation of the ClickHouse connection up into shared space, so
   it's only done once
3. Ideally, make it only happen if the appropriate environment variables are
   set (so we don't make the app depend on having a ClickHouse service)
4. Which means the `stats` page will need to do something sensible if there
   isn't a connection :)
   
---

Oh, it's in the
[documentation](https://clickhouse.com/docs/integrations/python#client-creation-examples) -
for `clickhouse_connect` I need to pass the `secure=True` parameter to ask it
to use HTTPS. And if I do that (and use the HTTPS port) then I can get a
connection.

So later on I shall convert the app code to using `clickhouse_connect`...
