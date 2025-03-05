# Kafka connectors

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

