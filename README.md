# Pushing this button does nothing

This is a fun interactive web application built with FastAPI that sends user click interactions to Apache Kafka, and from there to PostgreSQL and/or ClickHouse.

## Deploy Aiven Services

This project Kafka for data streaming with records being stored in PostgreSQL and ClickHouse. Using Aiven and [Terraform](https://www.terraform.io/)/[OpenTofu](https://opentofu.org/).

You will need to provide the following information to build your services with terraform.

## Est. Monthly Pricing

| service      | plan       | cost (google-europe-east1) | cost (google-europe-west2) |
| ------------ | ---------- | -------------------------- | -------------------------- |
| Apache Kafka | Business-4 | $500                       | $660                       |
| ClickHouse   | Startup-16 | $480                       | $590                       |
| PostgreSQL   | Startup-1  | $25                        | $25                        |

## Features

- Aggregation of users by country (ip-based) all done on platform with no ip information stored.
- Real-time data streaming to Apache Kafka
- HTMX to send user interactions updates without page reloads.
- Random humorous responses when the button is clicked

## Prerequisites

- Python 3.10+

We'll explain how to set up the necessary services:

## Installation

1. Clone the repository:

   ```
   git clone https://github.com/<YOURUSERNAME>/dont-push-the-button.git
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
