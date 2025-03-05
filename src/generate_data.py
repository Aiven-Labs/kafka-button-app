#!/usr/bin/env python3

"""Generate fake data."""

import asyncio
import datetime
import logging
import os
import pathlib
import pprint
import random

from enum import StrEnum
from typing import Iterator, Optional
from uuid import UUID, uuid4

import dotenv

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
dotenv.load_dotenv()

GEOIP_DATASET_FILENAME = 'geoip2fast-city-ipv6.dat.gz'


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

if False:
    certs_folder = pathlib.Path("certs")

    KAFKA_BOOTSTRAP_SERVER = os.getenv("AIVEN_KAFKA_SERVICE_ENDPOINT_URI", "localhost:9093")
    ssl_context = create_ssl_context(
        cafile=certs_folder / "ca.pem",
        certfile=certs_folder / "service.cert",
        keyfile=certs_folder / "service.key",
    )

    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVER,
        ssl_context=ssl_context,
    )


class Action(StrEnum):
    ENTER_PAGE = 'EnterPage'
    PRESS_BUTTON = 'PressButton'
    EXIT_PAGE = 'ExitPage'



class Event(BaseModel):
    session_id: UUID
    timestamp: float
    action: str
    country_name: str
    country_code: str
    subdivision_name: Optional[str] = None
    subdivision_code: Optional[str] = None
    city_name: Optional[str] = None


def generate_session() -> Iterator[Event]:
    """Yield button press message tuples from a single web app "session"

    Note we do *not* expose the IP address, as that counts as personal information.
    If we don't yield it in our datastructure, then there's no way we can leak it.
    """
    # I can't see a way of getting the lat, long for a city without using an internet
    # connection, so let's not do that, at least for the moment. The consumer end can
    # worry about that.

    session_id = uuid4()
    logging.info(f'Session {session_id}')
    # Our base time is NOW as a floating Unix timestamp, seconds since the epoch
    timestamp = datetime.datetime.now(datetime.timezone.utc).timestamp()

    if random.randint(1,3) == 3:    # or some other distribution
        #ip_address = fake.ipv6()
        ip_address = geoip.generate_random_ipv6_address()
    else:
        #ip_address = fake.ipv4()
        ip_address = geoip.generate_random_ipv4_address()

    try:
        geoip_data = geoip.lookup(ip_address)
    except GeoIPError as e:
        logging.error(f'IP lookup error: {e}')
        logging.error(f'Trying to lookup {ip_address}')
        return

    country_name = geoip_data.country_name
    country_code = geoip_data.country_code
    city_name = geoip_data.city.name
    subdivision_name = geoip_data.city.subdivision_name
    subdivision_code = geoip_data.city.subdivision_code
    logging.info(f'IP {ip_address} -> {country_name}, {country_code} ({city_name}, {subdivision_name}, {subdivision_code}')

    print(geoip_data.pp_json())

    # Most of our data stays the same, so we can handily use a dictionary
    data = {
        'session_id': session_id,
        'timestamp': timestamp,
        'action': str(Action.ENTER_PAGE),
        'country_name': country_name,
        'country_code': country_code,
        'subdivision_name': subdivision_name,
        'subdivision_code': subdivision_code,
        'city_name': city_name,
    }

    yield Event(**data)

    # Luckily we're not trying to be especially random, so this is good enough
    number_presses = random.randint(1, 10)
    data['action'] = str(Action.PRESS_BUTTON)
    for press in range(number_presses):
        # Pretend we have elapsed time between button presses
        timestamp += random.randint(500, 5000)
        logging.info(f'Press {press} at {timestamp}')

        data['timestamp'] = timestamp
        yield Event(**data)

    timestamp += random.randint(500, 5000)
    logging.info(f'Leave page at {timestamp}')

    data['timestamp'] = timestamp
    data['action'] = str(Action.EXIT_PAGE)
    yield Event(**data)



async def send_messages_to_kafka():
    pass

def main():
    #with asyncio.Runner() as runner:
    #    runner.run(send_messages_to_kafka)


    for event in generate_session():
        print(f'EVENT {event}')


if __name__ == '__main__':
    main()
