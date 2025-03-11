#!/usr/bin/env python3

"""An app to show a button that does "nothing", but does send events to Kafka.

Run for development with `fastapi dev app.py`, run for real with `fastapi run app.py`

The following must be provided, either as environment variables or in a `.env` file:

* KAFKA_SERVICE_URI - the URI for the Kafka bootstrap server
* SCHEMA_REGISTRY_URI - the URI for the Karapace schema service
"""

import datetime
import logging
import os
import pathlib
import random

from contextlib import asynccontextmanager
from typing import Optional, Any
from uuid import UUID, uuid4

import avro.schema
import dotenv

from aiokafka import AIOKafkaProducer
from aiokafka.helpers import create_ssl_context
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from geoip2fast import GeoIP2Fast
from pydantic import BaseModel

from .button_responses import BUTTON_RESPONSES

from .message_support import DEFAULT_TOPIC_NAME as TOPIC_NAME
from .message_support import Cookie
from .message_support import Action
from .message_support import Event
from .message_support import new_cookie
from .message_support import load_geoip_data
from .message_support import create_avro_schema
from .message_support import get_parsed_avro_schema
from .message_support import register_avro_schema
from .message_support import make_avro_payload

logging.basicConfig(level=logging.INFO)

# The geoip2fast dataset we want to use. Note that this is one we need to
# download ourselves.
GEOIP_DATASET_FILENAME = 'geoip2fast-city-ipv6.dat.gz'

# If there's a `.env` file, load it.
# If a value in the .env file already exists as a system environment variable,
# then use the system value. Otherwise take the value from the .env file.
dotenv.load_dotenv()

KAFKA_SERVICE_URI = os.getenv("KAFKA_SERVICE_URI")
SCHEMA_REGISTRY_URI = os.getenv("SCHEMA_REGISTRY_URI", None)

CERTS_FOLDER = pathlib.Path("certs")


class LifespanData:
    producer: AIOKafkaProducer
    geoip: GeoIP2Fast
    avro_schema: str
    parsed_avro_schema: avro.schema.RecordSchema
    avro_schema_id: int


lifespan_data = LifespanData()


async def start_producer() -> AIOKafkaProducer:
    """Start our Kafka producer."""
    ssl_context = create_ssl_context(
        cafile=CERTS_FOLDER / "ca.pem",
        certfile=CERTS_FOLDER / "service.cert",
        keyfile=CERTS_FOLDER / "service.key",
    )

    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_SERVICE_URI,
        security_protocol="SSL",
        ssl_context=ssl_context,
    )
    await producer.start()
    return producer


def setup_avro_schema():

    lifespan_data.avro_schema = create_avro_schema(TOPIC_NAME)

    # Parsing the schema both validates it, and also puts it into a form that
    # can be used when envoding/decoding message data
    lifespan_data.parsed_avro_schema = get_parsed_avro_schema(
        lifespan_data.avro_schema,
    )

    lifespan_data.avro_schema_id = register_avro_schema(
        SCHEMA_REGISTRY_URI,
        lifespan_data.avro_schema,
        TOPIC_NAME,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    lifespan_data.geoip = load_geoip_data()
    setup_avro_schema()
    lifespan_data.producer = await start_producer()
    yield
    await lifespan_data.producer.stop()


# Initialize FastAPI app
app = FastAPI(
    title="Don't Push the Button - Aiven for Apache Kafka Workshop",
    lifespan=lifespan,
)

# Set up templates
templates = Jinja2Templates(directory="templates")

session = uuid4()


class ClickInteraction(BaseModel):
    ip_address: str
    timestamp: datetime.datetime
    country: Optional[str] = None
    longitude: float = 0.0
    latitude: float = 0.0
    session: UUID = session

    def model_post_init(self, __context: Any) -> None:
        """Performs a lookup at the user's IP Address and returns the country of the user"""
        lookup = lifespan_data.geoip.lookup(self.ip_address)

        self.country = lookup.country_name
        self.longitude = 0.0
        self.latitude = 0.0


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request"""
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        # Get the first IP in the chain which is typically the client's true IP
        return x_forwarded_for.split(",")[0].strip()
    else:
        # If no X-Forwarded-For header, use the direct client's IP
        return request.client.host if request.client else "unknown"


# These will get moved to the top (or deleted if not needed) when things are working
import json
import uuid
from fastapi.responses import JSONResponse
from geoip2fast.geoip2fast import GeoIPError
from pydantic import ValidationError

COOKIE_NAME = 'button_press_session'
COOKIE_LIFETIME = 3600    # 1 hour

DEFAULT_COHORT = 0

FAKE_DATA = True


def get_ip_address(request: Request) -> str:
    ip_address = get_client_ip(request)
    if FAKE_DATA and ip_address == '127.0.0.1':
        # Because localhost isn't much fun...
        ip_address = lifespan_data.geoip.generate_random_ipv4_address()


async def send_avro_message(cookie: Cookie, action: Action):
    """Send an Avro encoded message based on the cookie."""

    event = Event(
        **dict(cookie),
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        action=action,
    )
    logging.info(f'Sending Avro message {event}')
    message_bytes = make_avro_payload(
        event,
        lifespan_data.avro_schema_id,
        lifespan_data.parsed_avro_schema,
    )
    # For the moment, don't let it buffer messages
    await lifespan_data.producer.send_and_wait(TOPIC_NAME, message_bytes)


@app.get("/reset", response_class=HTMLResponse)
async def reset(request: Request):
    """For development/debugging - reset any cookies when we're visited"""

    logging.info('HI HI RESET')
    logging.info(f'request.cookies {request.cookies}')
    logging.info(f'cookie {request.cookies.get(COOKIE_NAME)}')

    logging.info('Expiring cookie values')

    response = HTMLResponse("""\
    <html>
    <head><h1>Cookies are reset</h1></head>
    <body><p><a href="/">Back to the button</a></p>
    </html>
    """)
    response.delete_cookie(key=COOKIE_NAME)
    return response


def get_cookie_from_request(request: Request) -> Cookie:
    """Get the cookie from the request. If there isn't one, make a new one.
    """
    logging.info(f'Retrieving cookie {COOKIE_NAME}')
    cookie_str = request.cookies.get(COOKIE_NAME)
    if not cookie_str:
        logging.info(f'No cookie found: making new')
        cookie = new_cookie(lifespan_data.geoip, get_ip_address, request, DEFAULT_COHORT)
    else:
        logging.info(f'Found cookie value {cookie_str}')
        try:
            cookie = Cookie.model_validate_json(cookie_str)
        except ValidationError:
            logging.error(f'Unable to parse cookie {COOKIE_NAME} value {cookie_str}')
            cookie = new_cookie(lifespan_data.geoip, get_ip_address, request, DEFAULT_COHORT)
    return cookie


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """Render the main page with the button"""

    logging.info('HI HI INDEX')
    logging.info(f'request.cookies {request.cookies}')

    cookie = get_cookie_from_request(request)

    # Send our actual message to Kafka
    # The user has either come to this page for the first time, or they've refreshed it
    await send_avro_message(cookie, Action.ENTER_PAGE)

    context = {
        "request": request,
        "button_response": "Clicking this button does absolutely nothing.",
    }
    response = templates.TemplateResponse("index.html", context)

    # We always (re)set the cookie
    # If there wasn't one before, we need to set the new one now
    # If it already existed, we want to extend its lifetime
    cookie_str = cookie.model_dump_json()
    response.set_cookie(key=COOKIE_NAME, value=cookie_str, expires=COOKIE_LIFETIME)

    return response


@app.post("/send-ip", response_class=HTMLResponse)
async def send_ip(request: Request):
    """
    Endpoint that sends the IP to Kafka and returns the updated UI part
    This is triggered by HTMX
    """
    logging.info('HI HI BUTTON')
    logging.info(f'request.cookies {request.cookies}')

    cookie = get_cookie_from_request(request)

    ip_address = get_client_ip(request)
    interaction = ClickInteraction(
        ip_address=ip_address, timestamp=datetime.datetime.now(datetime.timezone.utc)
    )

    # Send our actual message to Kafka
    await send_avro_message(cookie, Action.PRESS_BUTTON)

    # Return only the updated part for HTMX to replace
    context = {
        "request": request,
        "button_response": random.choice(BUTTON_RESPONSES),
    }
    response = templates.TemplateResponse("partials/button_text.html", context)

    # We always (re)set the cookie
    # If there wasn't one before, we need to set the new one now
    # If it already existed, we want to extend its lifetime
    cookie_str = cookie.model_dump_json()
    response.set_cookie(key=COOKIE_NAME, value=cookie_str, expires=COOKIE_LIFETIME)

    return response
