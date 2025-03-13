# Pushing this button does nothing (really)

A fun interactive web application built with FastAPI that sends user click interactions to Apache Kafka.

If you want to play along, instructions are in [summary.md](summary.md). The intent is to fold them into this README at a later stage.

Development notes are in the [working-document.md](working-document.md) file, and will act as the basis for actual documentation.

## Overview

This project is a demonstration application for the Aiven for Apache Kafka
Workshop. It presents users with a button that claims to do nothing, then
captures and streams interaction data to Kafka when they inevitably push it.

## Features

- Interactive web interface with a tempting button
- Geo-location tracking of user clicks
- Real-time data streaming to Apache Kafka
  - and from there into PostgreSQL and ClickHouse
- HTMX for dynamic UI updates without page reloads
- Random humorous responses when the button is clicked

## Prerequisites

- Python 3.8+

We'll explain how to set up the necessary services:

- An [Aiven for Apache Kafka](https://aiven.io/kafka) service
- Optionally, an [Aiven for PostgreSQL®](https://aiven.io/postgresql) service
- Optionally, an [Aiven for ClickHouse®](https://aiven.io/clickhouse) service

and how to use the button app, and/or generate fake data.

## Installation

1. Clone the repository:

   ```
   git clone https://github.com/yourusername/dont-push-the-button.git
   cd dont-push-the-button
   ```

2. Create a virtual environment and install dependencies:

   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. For the moment, follow the [summary.md](summary.md) document for the rest.

## Project Structure

```
kafka-button-app/
├─LICENSE
├─README.md
├─requirements.txt
├─src/
│ ├─__init__.py
│ ├─app.py
│ ├─button_responses.py
│ ├─generate_data.py*
│ └─message_support.py
├─summary.md
├─templates/
│ ├─index.html
│ └─partials/
│   └─button_text.html
└─working-document.md
```

## How It Works

1. When a user visits the application, they are presented with a button
   they're told does nothing.
2. When they push the button, their IP address is captured and geo-located.
3. The interaction data (timestamp, country, coordinates, session ID) is
   serialized and sent to Kafka. The IP address is not sent anywhere, as it
   counts as personal data.
4. The button is dynamically updated with a random humorous message.

## Kafka Integration

The application uses `aiokafka` to produce messages to a Kafka topic. The messages contain:

- Timestamp of the interaction
- Session ID
- Country information (if available)

## Customization

You can customize the button responses by modifying the `BUTTON_RESPONSES` list in `app/button_responses.py`.

## Security Considerations

- The application uses SSL for secure Kafka connections
- IP addresses are processed but not stored persistently in the application
- Geo-location is done using the GeoIP2Fast library without external API calls

## Workshop Extensions

Some ideas for workshop participants:

1. Create a Kafka consumer to analyze click patterns
2. Add a real-time dashboard showing global button presses
3. Implement rate limiting to prevent spam clicking
4. Add more interactive elements based on geo-location data

## Troubleshooting

- **Connection issues with Kafka**: Verify your certificates and Kafka service endpoint URI
- **Geo-location not working**: Ensure the GeoIP2Fast database is properly initialized and you are not trying to connect to your service on a PRIVATE IP.
- **HTMX not updating**: Check browser console for JavaScript errors

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
