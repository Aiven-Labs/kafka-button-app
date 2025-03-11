#!/usr/bin/env python3

"""All the code we need to handle generating our messages."""

import datetime
import io
import json
import logging
import pprint
import struct
import uuid

from collections.abc import Callable
from enum import StrEnum
from typing import Optional, Any

import avro
import avro.io
import avro.schema
import httpx

from geoip2fast import GeoIP2Fast
from geoip2fast.geoip2fast import GeoIPError
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)


# The geoip2fast dataset we want to use. Note that this is one we need to
# download ourselves.
GEOIP_DATASET_FILENAME = 'geoip2fast-city-ipv6.dat.gz'


def load_geoip_data() -> GeoIP2Fast:
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


# We hard code the topic name.
# For this demo program, it's not worth the complexity of making it settable
# via the command line (that would need a fair amount of code reorganisation
# so that schema definition wasn't at the top level). We *could* allow it to
# be set via an environment variable, but haven't done so yet.
#
# Note that Avro schema names don't allow hyphens, and the JDBC connector
# (at least by default) wants the topic name and schema name to match
DEFAULT_TOPIC_NAME = "button_presses"


class Action(StrEnum):
    ENTER_PAGE = 'EnterPage'
    PRESS_BUTTON = 'PressButton'


class Cookie(BaseModel):
    session_id: str
    cohort: int | None
    country_name: str
    country_code: str
    subdivision_name: str    # may be ''
    subdivision_code: str    # may be ''
    city_name: str           # may be ''


def new_cookie(
        geoip: GeoIP2Fast,
        get_ip_address: Callable[[Any],str],
        request: Optional[Any]=None,
        cohort: Optional[int]=0,
) -> Cookie:
    """Calculate the cookie for a new 'session'


    * `geoip` is our GeoIP2Fast instance, which we use to look up IP addresses
        and get back location data
    * `get_ip_address` is a callable to get the IP address for this "session",
      It expects to be passed the `request` argument (for which see below).
    * `cohort` is a way of identifying a group in which that person is placed
        (one assumes a cohort of experimental subjects). The default it None.
        A value of None means that this data is produced by the fake data
        generator script.
    * `request` is the Request object in a real-life web app, and None otherwise.
      We don't try to typecheck it here, as it's only the callable that might
      care about it, and *that* might not actually want a Request after all,
      and we don't know what *sort* of Request :)
    """
    ip_address = get_ip_address(request)

    try:
        geoip_data = geoip.lookup(ip_address)
    except GeoIPError as e:
        logging.error(f'IP lookup error: {e}')
        logging.error(f'Trying to lookup {ip_address}')
        raise ValueError('Unable to retrieve IP data {e} for {ip_address}')

    return Cookie(
        session_id=str(uuid.uuid4()),
        cohort=cohort,
        country_name=geoip_data.country_name,
        country_code=geoip_data.country_code,
        subdivision_name=geoip_data.city.subdivision_name,
        subdivision_code=geoip_data.city.subdivision_code,
        city_name=geoip_data.city.name,
    )


class Event(BaseModel):
    session_id: str
    timestamp: str
    cohort: int | None
    action: str
    country_name: str
    country_code: str
    subdivision_name: str    # may be ''
    subdivision_code: str    # may be ''
    city_name: str           # may be ''


def create_avro_schema(topic_name: str=DEFAULT_TOPIC_NAME) -> str:
    """When we *use* the Avro schema, we need it as a string.
    """
    schema = {
        'doc': 'Web app interactions',
        'name': topic_name,
        'type': 'record',
        'fields': [
            {'name': 'session_id', 'type': 'string'},
            {'name': 'timestamp', 'type': 'string'},
            {'name': 'action', 'type': 'string'},
            {'name': 'country_name', 'type': 'string'},
            {'name': 'country_code', 'type': 'string'},
            {'name': 'subdivision_name', 'type': 'string'},
            {'name': 'subdivision_code', 'type': 'string'},
            {'name': 'city_name', 'type': 'string'},
            {'name': 'cohort', 'type': ['null', 'int'], 'default': 'null'},
        ],
    }
    return json.dumps(schema)


def get_parsed_avro_schema(schema_as_str: str) -> avro.schema.RecordSchema:
    # Parsing the schema both validates it, and also puts it into a form that
    # can be used when envoding/decoding message data
    return avro.schema.parse(schema_as_str)


def register_avro_schema(schema_uri: str, schema_as_str: str, topic_name: str) -> int:
    """Register our schema with Karapace.

    Returns the schema id, which gets embedded into the messages.
    """

    logging.info(f'Registering schema {topic_name}-value')
    r = httpx.post(
        f'{schema_uri}/subjects/{topic_name}-value/versions',
        json={"schema": schema_as_str}
    )
    r.raise_for_status()

    logging.info(f'Registered schema {r} {r.text=} {r.json()=}')
    response_json = r.json()
    return response_json['id']


def make_avro_payload(
        event: Event,
        schema_id: int,
        parsed_schema: avro.schema.RecordSchema,
) -> bytes:
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
    writer = avro.io.DatumWriter(parsed_schema)
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
