FROM python:3.11-slim

WORKDIR /app

COPY ./requirements.txt /app
COPY ./run.sh /app

RUN apt-get update &&\
    apt-get install -y jq

RUN python3 -m pip install --no-cache-dir -r requirements.txt

# Copy all our source code
COPY ./src /app/src

# Create somewhere for the Kafka certificates
RUN mkdir /app/certs

EXPOSE 3000
CMD [ "bash", "./run.sh" ]

#CMD [ "fastapi", "run", "src/app.py", "--port", "3000" ]
