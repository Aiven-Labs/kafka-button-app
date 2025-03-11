#!/usr/bin/env python3

"""Generate fake data."""

import argparse
import asyncio
import datetime
import logging
import os
import pathlib
import random

from typing import Iterator, Optional

import dotenv

from aiokafka import AIOKafkaProducer
from aiokafka.helpers import create_ssl_context
import avro.schema
from geoip2fast import GeoIP2Fast

from message_support import DEFAULT_TOPIC_NAME as TOPIC_NAME
from message_support import Event
from message_support import load_geoip_data
from message_support import create_avro_schema
from message_support import get_parsed_avro_schema
from message_support import register_avro_schema
from message_support import httpx
from message_support import EventCreator
from message_support import make_avro_payload


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


# Command line default values
DEFAULT_CERTS_FOLDER = "certs"
# Allow setting these defaults via a `.env` file as well
dotenv.load_dotenv()
KAFKA_SERVICE_URI = os.getenv("KAFKA_SERVICE_URI", "localhost:9093")
SCHEMA_REGISTRY_URI = os.getenv("SCHEMA_REGISTRY_URI", None)


# A `cohort` value of None means that the data comes from this data generator
FAKE_DATA_COHORT = None


def generate_session(geoip: GeoIP2Fast) -> Iterator[Event]:
    """Yield button press message tuples from a single web app "session"

    Note we do *not* expose the IP address, as that counts as personal information.
    If we don't yield it in our datastructure, then there's no way we can leak it.
    """
    # I can't see a way of getting the lat, long for a city without using an internet
    # connection, so let's not do that, at least for the moment. The consumer end can
    # worry about that.

    if random.randint(1,3) == 3:    # or some other distribution
        #ip_address = fake.ipv6()
        ip_address = geoip.generate_random_ipv6_address()
    else:
        #ip_address = fake.ipv4()
        ip_address = geoip.generate_random_ipv4_address()

    event_creator = EventCreator(ip_address, geoip, cohort=FAKE_DATA_COHORT)

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

    logging.info('Left page')



async def send_messages_to_kafka(
        kafka_uri: str,
        certs_dir: pathlib.Path,
        topic_name: str,
        schema_id: int,
        parsed_schema: avro.schema.RecordSchema,
        geoip: GeoIP2Fast,
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
        for event in generate_session(geoip):
            print(f'EVENT {event}')
            raw_bytes = make_avro_payload(event, schema_id, parsed_schema)
            # For the moment, don't let it buffer messages
            await producer.send_and_wait(topic_name, raw_bytes)
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

    geoip = load_geoip_data()

    schema = create_avro_schema(TOPIC_NAME)

    # Parsing the schema both validates it, and also puts it into a form that
    # can be used when envoding/decoding message data
    parsed_schema = get_parsed_avro_schema(schema)

    schema_id = register_avro_schema(args.schema_uri, schema, TOPIC_NAME)

    with asyncio.Runner() as runner:
        runner.run(send_messages_to_kafka(
            args.kafka_uri, args.certs_dir, TOPIC_NAME, schema_id, parsed_schema, geoip,
            ),
        )


if __name__ == '__main__':
    main()
