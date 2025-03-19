FROM python:3.11-slim

WORKDIR /app

COPY ./requirements.txt /app
COPY ./run.sh /app

RUN apt-get update &&\
    apt-get install -y curl jq

RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Copy all our source code
COPY ./src /app/src

# Create somewhere for the Kafka certificates
RUN mkdir /app/certs

# Download the geoip2fast dataset that knows about cities
# Note the `-L` (--location) to follow redirects, without which it won't work
## DISABLED FOR THE MOMENT
##RUN curl https://github.com/rabuchaim/geoip2fast/releases/download/LATEST/geoip2fast-city-ipv6.dat.gz -L --output /app/geoip2fast-city-ipv6.dat.gz

EXPOSE 3000
CMD [ "bash", "./run.sh" ]

#CMD [ "fastapi", "run", "src/app.py", "--port", "3000" ]
