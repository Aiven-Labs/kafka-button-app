#!/usr/bin/env python3

"""An app to show a button that does "nothing", but does send events to Kafka.

Run for development with `fastapi dev app.py`, run for real with `fastapi run app.py`

The following must be provided, either as environment variables or in a `.env` file:

* KAFKA_SERVICE_URI - the URI for the Kafka bootstrap server
* SCHEMA_REGISTRY_URI - the URI for the Karapace schema service
"""

import datetime
import json
import logging
import os
import pathlib
import random

from contextlib import asynccontextmanager
from typing import Optional, Any

import avro.schema
import clickhouse_connect
import dotenv
import httpx

from aiokafka import AIOKafkaProducer
from aiokafka.helpers import create_ssl_context
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from geoip2fast import GeoIP2Fast
from pydantic import BaseModel
from pydantic import ValidationError

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

# However, httpx will log all GET and POST requests at level INFO,
# includingthe full URI, with any embedded passwords :(
# We definitely want to disable that - for instance it would
# show our Karapace password when registering a schema
logging.getLogger("httpx").setLevel(logging.ERROR)


# If there's a `.env` file, load it.
# If a value in the .env file already exists as a system environment variable,
# then use the system value. Otherwise take the value from the .env file.
dotenv.load_dotenv()

KAFKA_SERVICE_URI = os.getenv("KAFKA_SERVICE_URI")
SCHEMA_REGISTRY_URI = os.getenv("SCHEMA_REGISTRY_URI", None)

# The ClickHouse connection information, for the `stats` page
CH_HOST = os.getenv("CH_HOST")
CH_PORT = int(os.getenv("CH_PORT"))  # this will be nasty if it's unset :(
CH_USERNAME = os.getenv("CH_USERNAME")
CH_PASSWORD = os.getenv("CH_PASSWORD")
CH_TABLE_NAME = os.getenv("CH_TABLE_NAME", "button_presses")

CERTS_FOLDER = pathlib.Path("certs")

COOKIE_NAME = "button_press_session"
COOKIE_LIFETIME = 3600  # 1 hour

DEFAULT_COHORT = 0

# If this is True, and the apparent IP address is 127.0.0.1 (localhost),
# then generate a fake IP address instead
FAKE_IP_IF_LOCALHOST = True


class LifespanData:
    producer: AIOKafkaProducer
    geoip: GeoIP2Fast
    avro_schema: str
    parsed_avro_schema: avro.schema.RecordSchema
    avro_schema_id: int
    ch_client: Optional[clickhouse_connect.driver.AsyncClient]


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


async def get_ch_client() -> clickhouse_connect.driver.AsyncClient:
    return await clickhouse_connect.get_async_client(
        host=CH_HOST,
        port=int(CH_PORT),
        user=CH_USERNAME,
        password=CH_PASSWORD,
        database="default",
        secure=True,
    )


def setup_avro_schema():

    lifespan_data.avro_schema = create_avro_schema(TOPIC_NAME)

    # Parsing the schema both validates it, and also puts it into a form that
    # can be used when envoding/decoding message data
    lifespan_data.parsed_avro_schema = get_parsed_avro_schema(
        lifespan_data.avro_schema,
    )

    lifespan_data.avro_schema_id = register_avro_schema(
        SCHEMA_REGISTRY_URI,
        TOPIC_NAME,
        lifespan_data.avro_schema,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    lifespan_data.geoip = load_geoip_data()
    setup_avro_schema()
    lifespan_data.producer = await start_producer()
    lifespan_data.ch_client = await get_ch_client()
    yield
    await lifespan_data.producer.stop()


# Initialize FastAPI app
app = FastAPI(
    title="Don't Push the Button - Aiven for Apache Kafka Workshop",
    lifespan=lifespan,
)

# Set up templates
templates = Jinja2Templates(directory="src/templates")


def get_client_ip(request: Request) -> str:
    """Extract client IP address from request"""
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        # Get the first IP in the chain which is typically the client's true IP
        return x_forwarded_for.split(",")[0].strip()
    else:
        # If no X-Forwarded-For header, use the direct client's IP
        return request.client.host if request.client else "unknown"


def get_ip_address(request: Request) -> str:
    ip_address = get_client_ip(request)
    if FAKE_IP_IF_LOCALHOST and ip_address == "127.0.0.1":
        # Because localhost isn't much fun...
        ip_address = lifespan_data.geoip.generate_random_ipv4_address()
        logging.info(
            f"We're at 1227.0.0.1 which is boring; pretending to be at {ip_address}"
        )
    return ip_address


async def send_avro_message(cookie: Cookie, action: Action):
    """Send an Avro encoded message based on the cookie."""

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    microseconds_since_epoch = int(now_utc.timestamp() * 1000_000)

    event = Event(
        **dict(cookie),
        timestamp=microseconds_since_epoch,
        action=action,
    )
    logging.info(f"Sending Avro message {event}")
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

    logging.info("HI HI RESET")
    logging.info(f"request.cookies {request.cookies}")
    logging.info(f"cookie {request.cookies.get(COOKIE_NAME)}")

    logging.info("Expiring cookie values")

    response = HTMLResponse(
        """\
    <html>
    <head><h1>Cookies are reset</h1></head>
    <body><p><a href="/">Back to the button</a></p>
    </html>
    """
    )
    response.delete_cookie(key=COOKIE_NAME)
    return response


def get_cookie_from_request(request: Request) -> Cookie:
    """Get the cookie from the request. If there isn't one, make a new one."""
    logging.info(f"Retrieving cookie {COOKIE_NAME}")
    cookie_str = request.cookies.get(COOKIE_NAME)
    if not cookie_str:
        logging.info(f"No cookie found: making new")
        cookie = new_cookie(
            lifespan_data.geoip, get_ip_address, request, DEFAULT_COHORT
        )
    else:
        logging.info(f"Found cookie value {cookie_str}")
        try:
            cookie = Cookie.model_validate_json(cookie_str)
        except ValidationError:
            logging.error(f"Unable to parse cookie {COOKIE_NAME} value {cookie_str}")
            cookie = new_cookie(
                lifespan_data.geoip, get_ip_address, request, DEFAULT_COHORT
            )
    return cookie


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """Render the main page with the button"""

    logging.info("HI HI INDEX")
    logging.info(f"request.cookies {request.cookies}")

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


@app.post("/send-event", response_class=HTMLResponse)
async def send_event(request: Request):
    """
    Endpoint that sends a button press event to Kafka and returns the updated UI part
    This is triggered by HTMX
    """
    logging.info("HI HI BUTTON")
    logging.info(f"request.cookies {request.cookies}")

    cookie = get_cookie_from_request(request)

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


@app.get("/stats", response_class=HTMLResponse)
async def get_ch_stats(request: Request):
    """Report statistics from ClickHouse."""

    logging.info("HI HI ClickHouse stats page")
    logging.info(f"request.cookies {request.cookies}")

    cookie = get_cookie_from_request(request)
    cookie_dict = dict(cookie)

    parameters = {
        "table": CH_TABLE_NAME,
        "session_id": cookie_dict["session_id"],
    }
    result = await lifespan_data.ch_client.command(
        "SELECT COUNT(*) FROM {table:Identifier}"
        " WHERE session_id = {session_id:String} AND action == 'PressButton'",
        parameters=parameters,
    )
    count_for_this_session = result

    parameters = {
        "table": CH_TABLE_NAME,
        "country_name": cookie_dict["country_name"],
    }
    result = await lifespan_data.ch_client.command(
        "SELECT COUNT(*) FROM {table:Identifier}"
        " WHERE country_name = {country_name:String} AND action == 'PressButton'",
        parameters=parameters,
    )
    count_for_this_country = result

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    one_hour_ago = now_utc - datetime.timedelta(hours=1)
    microseconds_since_epoch = int(one_hour_ago.timestamp() * 1000_000)

    parameters = {
        "table": CH_TABLE_NAME,
        "country_name": cookie_dict["country_name"],
        "one_hour_ago": microseconds_since_epoch,
    }
    result = await lifespan_data.ch_client.command(
        "SELECT COUNT(*) FROM {table:Identifier}"
        " WHERE country_name = {country_name:String}"
        " AND action == 'PressButton'"
        " AND timestamp > {one_hour_ago:DateTime64(6,'UTC')}",
        parameters=parameters,
    )
    count_for_this_hour = result

    context = {
        "request": request,
        "cookie": cookie,
        "cookie_dict": cookie_dict,
        "count_for_this_country": count_for_this_country,
        "count_for_this_session": count_for_this_session,
        "count_for_this_hour": count_for_this_hour,
    }

    response = templates.TemplateResponse("stats.html", context)
    return response
