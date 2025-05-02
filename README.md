# Pushing this button (probably) does nothing

This is a fun interactive web application built with FastAPI that sends user click
interactions to Apache Kafka, and from there to PostgreSQL and/or ClickHouse.

## Deploy Aiven Services

This project Kafka for data streaming with records being stored in PostgreSQL and
ClickHouse. Using Aiven and [Terraform](https://www.terraform.io/)/[OpenTofu](https://opentofu.org/).

You will need to provide the following information to build your services with terraform.

## Est. Monthly Pricing

| service      | plan       | cost (google-us-east1) | cost (google-europe-west2) |
| ------------ | ---------- | ---------------------- | -------------------------- |
| Apache Kafka | Business-4 | $500                   | $660                       |
| ClickHouse   | Startup-16 | $480                   | $590                       |
| PostgreSQL   | Startup-1  | $25                    | $25                        |

## Features

- Aggregation of users by country (ip-based) all done on platform with no ip information stored.
- Real-time data streaming to Apache Kafka
- HTMX to send user interactions updates without page reloads.
- Random humorous responses when the button is clicked

## Prerequisites

- Python 3.11+
- [Terraform](https://developer.hashicorp.com/terraform/install) or
  [OpenTofu](https://opentofu.org/docs/intro/install/)
  (use `tofu` command instead of `terraform` if using OpenTofu)
- [psql]
- [clickhouse client](https://clickhouse.com/docs/interfaces/cli)

> **WARNING**
> If using MacOS and install Clickhouse via homebrew, you will need to verify your
> installation of Clickhouse client in `settings -> security` to allow network
> connections.

## Getting Started

- set your environment variables for terraform. This includes your
  [API Token](https://aiven.io/docs/platform/howto/create_authentication_token),
  Your [Aiven Cloud Location](https://aiven.io/docs/platform/reference/list_of_clouds)
  and your project_name.

  ```shell
  # for terraform
  TF_VAR_aiven_project_name="<PROJECT_NAME>"
  TF_VAR_cloud_name="<AIVEN_CLOUD_NAME>"
  TF_VAR_aiven_api_token="<AIVEN_API_TOKEN>"

  # for run.sh and our setup scripts
  AIVEN_TOKEN=$TF_VAR_aiven_api_token
  PROJECT_NAME=$TF_VAR_aiven_project_name
  ```

- terraform plan/apply (make sure you point to the `infra` directory)

  ```shell
  terraform -chdir=infra plan
  ```
  ```shell
  terraform -chdir=infra apply -auto-approve
  ```

- get your variables from terraform and set_variables

  ```shell
  ./setup_scripts/create_env_file.sh
  source terraform_env.sh
  ```

- create PostgreSQL and ClickHouse Tables

  ```shell
  ./setup_scripts/create_pg_tables.sh
  ./setup_scripts/create_clickhouse_tables.sh
  ```

- Create a virtual environment and install dependencies:

  ```shell
  python -m venv venv
  source venv/bin/activate  # On Windows: venv\Scripts\activate
  pip install -r requirements.txt
  ```

- start fastAPI

  ```python
  fastapi dev src/app.py --reload
  ```

### How the App Works

1. When a user visits the application, they are presented with a button
   they're told does nothing.
2. When they push the button, their IP address is captured and
   geo-located.
3. The interaction data (timestamp, country, coordinates, session ID) is
   serialized and sent to Kafka. The IP address is not sent anywhere, as it
   counts as personal data.
4. The button is dynamically updated with a random humorous message.

## Security Considerations

- The application uses SSL for secure Kafka connections
- IP addresses are processed but not stored persistently in the application
- Geo-location is done using the GeoIP2Fast library without external API calls

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
