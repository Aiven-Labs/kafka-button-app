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

