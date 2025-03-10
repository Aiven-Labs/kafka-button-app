#!/usr/bin/env python3

"""An app to show a button that does "nothing", but does send events to Kafka.

Run for development with `fastapi dev app.py`, run for real with `fastapi run app.py`

The following must be provided, either as environment variables or in a `.env` file:

* KAFKA_SERVICE_URI - the URI for the Kafka bootstrap server
* SCHEMA_REGISTRY_URI - the URI for the Karapace schema service
"""
# main.py
import json
import pathlib
import os
from contextlib import asynccontextmanager
import asyncio
import datetime
import logging
import random
from typing import Any, Optional
from uuid import UUID, uuid4

import dotenv
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.helpers import create_ssl_context
from fastapi import BackgroundTasks, FastAPI, Request, Cookie
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from geoip2fast import GeoIP2Fast
from pydantic import BaseModel

from .button_responses import BUTTON_RESPONSES

logging.basicConfig(level=logging.INFO)


dotenv.load_dotenv()

GEOIP_DATASET_FILENAME = "geoip2fast-city-ipv6.dat.gz"
KAFKA_SERVICE_URI = os.getenv("KAFKA_SERVICE_URI", "localhost:9090")
SCHEMA_REGISTRY_URI = os.getenv("SCHEMA_REGISTRY_URI", None)
SESSION_EXPIRY_SECONDS = 300  # 5 minutes
CERTS_FOLDER = pathlib.Path("certs")
SSL_CONTEXT = create_ssl_context(
    cafile=CERTS_FOLDER / "ca.pem",
    certfile=CERTS_FOLDER / "service.cert",
    keyfile=CERTS_FOLDER / "service.key",
)


def json_deserializer(key_data):
    if key_data is None:
        return None
    return json.loads(key_data.decode("utf-8"))


key_deserializer = json_deserializer
value_deserializer = json_deserializer


async def start_producer() -> AIOKafkaProducer:
    """Start our Kafka producer."""
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_SERVICE_URI,
        security_protocol="SSL",
        ssl_context=SSL_CONTEXT,
    )
    return producer


async def start_consumer() -> AIOKafkaConsumer:
    consumer = AIOKafkaConsumer(
        "click_interactions",
        bootstrap_servers=KAFKA_SERVICE_URI,
        security_protocol="SSL",
        ssl_context=SSL_CONTEXT,
        key_deserializer=json_deserializer,
        value_deserializer=json_deserializer,
    )

    await consumer.start()
    await consumer.seek_to_beginning()
    return consumer


@asynccontextmanager
async def lifespan(app: FastAPI):

    app.producer = await start_producer()
    app.consumer = await start_consumer()

    try:
        yield
    finally:
        logging.info("Shutting Down Producer")
        await app.producer.stop()
        await app.consumer.stop()


# Initialize FastAPI app
app = FastAPI(
    title="Don't Push the Button - Aiven for Apache Kafka Workshop",
    lifespan=lifespan,
)

# Initialize FastAPI app
templates = Jinja2Templates(directory="src/templates")
geoip = GeoIP2Fast()


class ClickInteraction(BaseModel):
    ip_address: str
    timestamp: datetime.datetime
    session: Optional[str] = None
    country: Optional[str] = None
    longitude: float = 0.0
    latitude: float = 0.0

    def model_post_init(self, __context: Any) -> None:
        """Performs a lookup at the user's IP Address and returns the country of the user"""
        lookup = geoip.lookup(self.ip_address)

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


@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request, session_id: UUID = Cookie(None)):
    """Render the main page with the button"""

    context = {
        "request": request,
        "button_response": "Clicking this button does absolutely nothing",
    }

    response = templates.TemplateResponse("index.html", context)

    if session_id is None:
        session_id = uuid4()

    expires = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(
        seconds=SESSION_EXPIRY_SECONDS
    )
    response.set_cookie(
        key="session_id",
        value=str(session_id),
        expires=expires,
        max_age=SESSION_EXPIRY_SECONDS,
        path="/",
        httponly=True,
        samesite="lax",
    )

    return response


async def send_message(producer: AIOKafkaProducer, message: str):
    await producer.send_and_wait("click_interactions", message)


@app.post("/send-ip", response_class=HTMLResponse)
async def send_ip(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Endpoint that sends the IP to Kafka and returns the updated UI part
    This is triggered by HTMX
    """
    ip_address = get_client_ip(request)
    interaction = ClickInteraction(
        ip_address=ip_address,
        session=request.cookies["session_id"],
        timestamp=datetime.datetime.now(datetime.timezone.utc),
    )

    # Send to Kafka
    message = interaction.model_dump_json(exclude={ip_address})
    await send_message(app.producer, message)

    # Return only the updated part for HTMX to replace
    context = {"request": request, "button_response": random.choice(BUTTON_RESPONSES)}

    return templates.TemplateResponse("partials/button_text.html", context)


async def get_messages(consumer):
    """Consumes data from the topic and returns new lines as they come in"""

    await consumer.seek_to_beginning()

    try:
        async for msg in consumer:
            await asyncio.sleep(2.5)
            yield f"data: {datetime.datetime.fromtimestamp(msg.timestamp/1000)}: {msg.value}\n\n"
    except asyncio.CancelledError:
        # Handle cancellation gracefully
        yield """event: close
                data: Connection closed by server\n\n"""
        logging.info("Stream connection cancelled")
        raise
    finally:
        # Clean up resources if needed
        yield """event: close
                data: Connection closed by server\n\n"""


@app.get("/click-log", response_class=StreamingResponse)
async def log_from_kafka():
    response = StreamingResponse(
        get_messages(consumer=app.consumer), media_type="text/event-stream"
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response
