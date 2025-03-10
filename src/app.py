#!/usr/bin/env python3

"""An app to show a button that does "nothing", but does send events to Kafka.

Run for development with `fastapi dev app.py`, run for real with `fastapi run app.py`

The following must be provided, either as environment variables or in a `.env` file:

* KAFKA_SERVICE_URI - the URI for the Kafka bootstrap server
* SCHEMA_REGISTRY_URI - the URI for the Karapace schema service
"""
# main.py
import pathlib
import os
from contextlib import asynccontextmanager
import datetime
import logging
import random
from typing import Optional, Any
from uuid import UUID, uuid4

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.producer = await start_producer()
    yield
    await app.producer.stop()


# Initialize FastAPI app
app = FastAPI(
    title="Don't Push the Button - Aiven for Apache Kafka Workshop",
    lifespan=lifespan,
)

# Set up templates
templates = Jinja2Templates(directory="templates")
#app.mount("/static", StaticFiles(directory="static"), name="static")

session = uuid4()
geoip = GeoIP2Fast()


class ClickInteraction(BaseModel):
    ip_address: str
    timestamp: datetime.datetime
    country: Optional[str] = None
    longitude: float = 0.0
    latitude: float = 0.0
    session: UUID = session

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
async def get_index(request: Request):
    """Render the main page with the button"""

    context = {
        "request": request,
        "button_response": "Clicking this button does absolutely nothing.",
    }

    return templates.TemplateResponse("index.html", context)


@app.post("/send-ip", response_class=HTMLResponse)
async def send_ip(request: Request):
    """
    Endpoint that sends the IP to Kafka and returns the updated UI part
    This is triggered by HTMX
    """
    ip_address = get_client_ip(request)
    interaction = ClickInteraction(
        ip_address=ip_address, timestamp=datetime.datetime.now(datetime.timezone.utc)
    )

    # Send to Kafka
    # Create message with IP and timestamp
    message = interaction.model_dump_json(exclude=ip_address)
    logging.info(message)
    # Send to Kafka

    # Return only the updated part for HTMX to replace

    context = {"request": request, "button_response": random.choice(BUTTON_RESPONSES)}

    return templates.TemplateResponse("partials/button_text.html", context)
