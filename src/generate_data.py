#!/usr/bin/env python3

"""Generate fake data."""

import argparse
import asyncio
import datetime
import io
import json
import logging
import os
import pathlib
import pprint
import random
import struct

from enum import StrEnum
from typing import Iterator, Optional
from uuid import UUID, uuid4

import avro
import avro.io
import avro.schema
import dotenv
import httpx

from aiokafka import AIOKafkaProducer
from aiokafka.helpers import create_ssl_context
from geoip2fast import GeoIP2Fast
from geoip2fast.geoip2fast import GeoIPError
from pydantic import BaseModel

# Since geoip2fast has IP address generation methods, we don't need Faker
# The DOWNSIDE is that the geoip2fast methods only generate IP addresses that
# exist in the GeoIP2Fast data files, so we won't get any unrecognised addresses.
#
# This is probably OK for at least intial testing, but does mean we won't
# know what might happen in all Real Life cases.
#
#from faker import Faker
#from faker.providers import internet

#fake = Faker()
#fake.add_provider(internet)

logging.basicConfig(level=logging.INFO)

GEOIP_DATASET_FILENAME = 'geoip2fast-city-ipv6.dat.gz'


# Command line default values
DEFAULT_CERTS_FOLDER = "certs"
# Allow setting these defaults via a `.env` file as well
dotenv.load_dotenv()
KAFKA_SERVICE_URI = os.getenv("KAFKA_SERVICE_URI", "localhost:9093")
SCHEMA_REGISTRY_URI = os.getenv("SCHEMA_REGISTRY_URI", None)

# We hard code the topic name.
# For this demo program, it's not worth the complexity of making it settable
# via the command line (that would need a fair amount of code reorganisation
# so that schema definition wasn't at the top level). We *could* allow it to
# be set via an environment variable, but haven't done so yet.
#
# Note that Avro schema names don't allow hyphens, and the JDBC connector
# (at least by default) wants the topic name and schema name to match
TOPIC_NAME = "button_presses"


class Action(StrEnum):
    ENTER_PAGE = 'EnterPage'
    PRESS_BUTTON = 'PressButton'
    EXIT_PAGE = 'ExitPage'


class Event(BaseModel):
    session_id: str
    timestamp: str
    action: str
    count: int
    country_name: str
    country_code: str
    subdivision_name: str    # may be ''
    subdivision_code: str    # may be ''
    city_name: str           # may be ''


AVRO_SCHEMA = {
    'doc': 'Web app interactions',
    'name': TOPIC_NAME,
    'type': 'record',
    'fields': [
        {'name': 'session_id', 'type': 'string'},
        {'name': 'timestamp', 'type': 'string'},
        {'name': 'action', 'type': 'string'},
        {'name': 'count', 'type': 'int'},
        {'name': 'country_name', 'type': 'string'},
        {'name': 'country_code', 'type': 'string'},
        {'name': 'subdivision_name', 'type': 'string'},
        {'name': 'subdivision_code', 'type': 'string'},
        {'name': 'city_name', 'type': 'string'},
    ],
}


# When we're passing the Avro schema around, we need to pass it as a string
AVRO_SCHEMA_AS_STR = json.dumps(AVRO_SCHEMA)


# Parsing the schema both validates it, and also puts it into a form that
# can be used when envoding/decoding message data
PARSED_SCHEMA = avro.schema.parse(AVRO_SCHEMA_AS_STR)


def register_schema(schema_uri):
    """Register our schema with Karapace.

    Returns the schema id, which gets embedded into the messages.
    """

    logging.info(f'Registering schema {TOPIC_NAME}-value')
    r = httpx.post(
        f'{schema_uri}/subjects/{TOPIC_NAME}-value/versions',
        json={"schema": AVRO_SCHEMA_AS_STR}
    )
    r.raise_for_status()

    logging.info(f'Registered schema {r} {r.text=} {r.json()=}')
    response_json = r.json()
    return response_json['id']


def make_avro_payload(event: Event, schema_id: int) -> bytes:
    """Given an Event, and a schema id, return an Avro payload.

    We assume the following:

    * Use of `io.aiven.connect.jdbc.JdbcSinkConnector`
      (https://github.com/aiven/jdbc-connector-for-apache-kafka/blob/master/docs/sink-connector.md)
      to consume data from Kafka and write it to PostgreSQL. This is an Apache 2 licensed fork of
      the Confluent `kafka-connect-jdbc` sink connector, from before it changed license
      (the Confluent connector is no longer Open Source).
    * Use of Karapace (https://www.karapace.io/) as our (open source) schema repository
    * [Apache Avro™](https://avro.apache.org/) to serialize the messages. To each message
      we'll also add the schema id.
    * The JDBC sink connector will then "unpick" the message using the
      `io.confluent.connect.avro.AvroConverter` connector
      (https://github.com/confluentinc/schema-registry/blob/master/avro-converter/src/main/java/io/confluent/connect/avro/AvroConverter.java)
      whose source code is Apache License, Version 2.0 licensed.
    """
    # The Avro encoder works by writing to a "file like" object,
    # so we shall use a BytesIO instance.
    writer = avro.io.DatumWriter(PARSED_SCHEMA)
    byte_data = io.BytesIO()

    # The JDBC Connector needs us to put the schema id on the front of each Avro message.
    # We need to prepend a 0 byte and then the schema id as a 4 byte value.
    # We'll just do this by hand using the Python `struct` library.
    header = struct.pack('>bI', 0, schema_id)
    byte_data.write(header)

    # And then we add the actual data
    encoder = avro.io.BinaryEncoder(byte_data)
    writer.write(dict(event), encoder)
    raw_bytes = byte_data.getvalue()

    return raw_bytes


def load_geoip_data():
    try:
        geoip = GeoIP2Fast(geoip2fast_data_file=GEOIP_DATASET_FILENAME)
    except Exception:
        # Download the city data
        # We DO NOT want to do this in a web application! In that situation, we should download
        # the file separately from the release directory - so getting
        # https://github.com/rabuchaim/geoip2fast/releases/download/LATEST/geoip2fast-city-asn-ipv6.dat.gz
        logging.info('Downloading city IP data')
        G = GeoIP2Fast()
        G.update_file(GEOIP_DATASET_FILENAME)
        geoip = GeoIP2Fast(geoip2fast_data_file=GEOIP_DATASET_FILENAME)

    print('Database info:')
    pprint.pp(geoip.get_database_info())

    return geoip


GEOIP = load_geoip_data()


class EventCreator:
    """A way of creating a sequence of linked events, with shared data.
    """

    def __init__(self, ip_address: str):
        """Perform the basic setup of a sequence of session events."""

        self.session_id = str(uuid4())
        logging.info(f'Session {self.session_id}')

        try:
            geoip_data = GEOIP.lookup(ip_address)
        except GeoIPError as e:
            logging.error(f'IP lookup error: {e}')
            logging.error(f'Trying to lookup {ip_address}')
            raise ValueError('Unable to retrieve IP data {e} for {ip_address}')

        self.country_name = geoip_data.country_name
        self.country_code = geoip_data.country_code
        self.city_name = geoip_data.city.name
        self.subdivision_name = geoip_data.city.subdivision_name
        self.subdivision_code = geoip_data.city.subdivision_code

        self.count = 0

    def new_event(self, action: Action) -> Event:
        # Our "now" in UTC as an ISO format string
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return Event(
            session_id = self.session_id,
            timestamp = now,
            action = str(action),
            count = self.count,
            country_name = self.country_name,
            country_code = self.country_code,
            subdivision_name = self.subdivision_name,
            subdivision_code = self.subdivision_code,
            city_name = self.city_name,
        )

    def enter_page(self) -> Event:
        """Return our page entry event"""
        # Because we're just entering the page, our count is 0
        self.count = 0
        return self.new_event(Action.ENTER_PAGE)

    def press_button(self) -> Event:
        """Return a button press event"""
        self.count += 1
        return self.new_event(Action.PRESS_BUTTON)


    def exit_page(self) -> Event:
        """Return our page exit event"""
        self.count += 1
        return self.new_event(Action.EXIT_PAGE)


def generate_session() -> Iterator[Event]:
    """Yield button press message tuples from a single web app "session"

    Note we do *not* expose the IP address, as that counts as personal information.
    If we don't yield it in our datastructure, then there's no way we can leak it.
    """
    # I can't see a way of getting the lat, long for a city without using an internet
    # connection, so let's not do that, at least for the moment. The consumer end can
    # worry about that.

    if random.randint(1,3) == 3:    # or some other distribution
        #ip_address = fake.ipv6()
        ip_address = GEOIP.generate_random_ipv6_address()
    else:
        #ip_address = fake.ipv4()
        ip_address = GEOIP.generate_random_ipv4_address()

    event_creator = EventCreator(ip_address)

    # We start with an EnterPage event
    enter_page = event_creator.enter_page()
    # But remember to use our own idea of what time it is
    fake_now = datetime.datetime.now(datetime.timezone.utc)
    enter_page.timestamp = fake_now.isoformat()
    yield enter_page

    # Luckily we're not trying to be especially random, so this is good enough
    number_presses = random.randint(1, 10)
    for press in range(number_presses):
        fake_now += datetime.timedelta(milliseconds=random.randint(500, 5000))
        logging.info(f'Press {press} at {fake_now}')

        press_button = event_creator.press_button()
        # Pretend we have elapsed time between button presses
        press_button.timestamp = fake_now.isoformat()
        yield press_button

    logging.info(f'Leave page at {fake_now}')

    # And at the end, the event `count` field reflects the total number of events for this session
    exit_page = event_creator.exit_page()
    # Remember we're pretending time is elapsing
    fake_now += datetime.timedelta(milliseconds=random.randint(500, 5000))
    exit_page.timestamp = fake_now.isoformat()
    yield exit_page


async def send_messages_to_kafka(
        kafka_uri: str,
        certs_dir: pathlib.Path,
        schema_id: int,
):
    ssl_context = create_ssl_context(
        cafile=certs_dir / "ca.pem",
        certfile=certs_dir / "service.cert",
        keyfile=certs_dir / "service.key",
    )

    producer = AIOKafkaProducer(
        bootstrap_servers=kafka_uri,
        security_protocol="SSL",
        ssl_context=ssl_context,
    )

    await producer.start()

    try:
        for event in generate_session():
            print(f'EVENT {event}')
            raw_bytes = make_avro_payload(event, schema_id)
            # For the moment, don't let it buffer messages
            await producer.send_and_wait(TOPIC_NAME, raw_bytes)
    finally:
        await producer.stop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-k', '--kafka-uri', default=KAFKA_SERVICE_URI,
        help='the URI for the Kafka service, defaulting to $KAFKA_SERVICE_URI'
        ' if that is set',
    )
    parser.add_argument(
        '-d', '--certs-dir', default=DEFAULT_CERTS_FOLDER, type=pathlib.Path,
        help=f'directory containing the ca.pem, service.cert and service.key'
        ' files, default "{DEFAULT_CERTS_FOLDER}"',
    )
    parser.add_argument(
        '-s', '--schema-uri', default=SCHEMA_REGISTRY_URI,
        help='the URI for the Karapace schema registry, defaulting to'
        ' $SCHEMA_REGISTRY_URI if that is set',
        )

    args = parser.parse_args()

    if args.kafka_uri is None:
        print('The URI for the Kafka service is required')
        print('Set KAFKA_SERVICE_URI or use the -k switch')
        logging.error('The URI for the Kafka service is required')
        logging.error('Set KAFKA_SERVICE_URI or use the -k switch')
        return -1

    if args.schema_uri is None:
        print('The URI for the Karapace schema registry is required')
        print('Set SCHEMA_REGISTRY_URI or use the -s switch')
        logging.error('The URI for the Karapace schema registry is required')
        logging.error('Set SCHEMA_REGISTRY_URI or use the -s switch')
        return -1

    load_geoip_data()

    schema_id = register_schema(args.schema_uri)

    with asyncio.Runner() as runner:
        runner.run(send_messages_to_kafka(
            args.kafka_uri, args.certs_dir, schema_id,
            ),
        )




if __name__ == '__main__':
    main()
