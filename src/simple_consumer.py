#!/usr/bin/env python3

"""A standalone script to read our button press messages from Kafka

Use CTRL-C to stop it :)
"""

import argparse
import asyncio
import datetime
import logging
import os
import pathlib

import avro.schema
import dotenv

from aiokafka import AIOKafkaConsumer
from aiokafka.helpers import create_ssl_context

from message_support import DEFAULT_TOPIC_NAME as TOPIC_NAME
from message_support import Event
from message_support import unpack_avro_payload

logging.basicConfig(level=logging.INFO)

# Command line default values
DEFAULT_CERTS_FOLDER = "certs"
# Allow setting these defaults via a `.env` file as well
dotenv.load_dotenv()
KAFKA_SERVICE_URI = os.getenv("KAFKA_SERVICE_URI")
SCHEMA_REGISTRY_URI = os.getenv("SCHEMA_REGISTRY_URI", None)

CERTS_FOLDER = pathlib.Path("certs")


async def read_messages_from_kafka(
        kafka_uri: str,
        schema_uri: str,
        certs_dir: pathlib.Path,
        topic_name: str,
        start_at_end: bool,
):
    ssl_context = create_ssl_context(
        cafile=certs_dir / "ca.pem",
        certfile=certs_dir / "service.cert",
        keyfile=certs_dir / "service.key",
    )

    consumer = AIOKafkaConsumer(
        topic_name,
        bootstrap_servers=kafka_uri,
        security_protocol="SSL",
        ssl_context=ssl_context,
    )

    await consumer.start()

    if start_at_end:
        print('Seeking to end')
        try:
            await consumer.seek_to_end()
        except Exception as e:
            print(f'Consumer seek-to-end exception {e.__class__.__name__} {e}')
            return
    else:
        print('Seeking to beginning')
        try:
            await consumer.seek_to_beginning()
        except Exception as e:
            print(f'Consumer seek-to-beginning exception {e.__class__.__name__} {e}')
            return

    cached_schema = {}
    try:
        while True:
            async for message in consumer:
                event = await unpack_avro_payload(
                    message.value,
                    schema_uri,
                    cached_schema,
                )
                timestamp_seconds = float(event.timestamp) / 1_000_000
                timestamp_str = datetime.datetime.fromtimestamp(timestamp_seconds, datetime.timezone.utc)
                print(event.to_str('4bbef6d9-64f5-421a-a3aa-0ce1ae217886'))
    #except Exception as e:
    #    print(f'Exception receiving message {e.__class__.__name__} {e}')
    finally:
        print(f'Consumer stopping')
        await consumer.stop()
        print(f'Consumer stopped')


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
    parser.add_argument(
        '-e', '--start-at-end', action='store_true',
        help='start reading from the most recent message',
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

    with asyncio.Runner() as runner:
        runner.run(
            read_messages_from_kafka(
                args.kafka_uri,
                args.schema_uri,
                args.certs_dir,
                TOPIC_NAME,
                args.start_at_end,
            ),
        )


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nCTRL-C')
