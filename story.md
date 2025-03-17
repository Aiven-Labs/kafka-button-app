# Workshop story

...working out the story before I commit to slides

Show the app and get people to press buttons
* show the Kafka stream (either by looking at the app page if we've got one,
  or by showing the output of the simple consumer app)
* show the app `stats` page
* mention how long the app will keep running

Note that all of the code and instructions how to use it are in the GitHub
repository, so people should feel free to play with it later on.
* And also that the repository will evolve to add more interesting things over
  time, so keep an eye out.

Show a picture of the architecture of the system as a whole
* app -> Kafka -> PG / CH / simple consumer

Things a mad data scientist might want to research
* How often someone presses the button, and how long they continue to do so in
  a single session
* How their location in the world affects this
* How the time of day affects this (we store time as UTC, but with the
  location we can work the local time out, more or less)
* How the use of the app spreads over time - can we map the spread of a
  (hopefully) viral phenomenon?
* And conversely, how long before the app becomes boring and no-one wants to
  use it any more.
* So later on, maybe we do A/B testing on how to affect button pressing by
  changing the app design!

Problems:
* GDPR and other equivalents mean we can't store the IP address
* IP addresses can't 100% reliably give a physical location
* We don't want the app to be going to the internet to look up the IP
  address - time and money considerations
* But we *can* get statistics on how reliable the location lookup is, and we
  are data scientists, so that's probably OK
* We'd like to have a representative lat/long for the location, but that would
  (at the moment) require a call out to another service. That's a candidate
  for data entrichment (which we'll maybe talk about later)
* It's a problem to identify "the same person", and there are considerations
  on how we can do that with a cookie (which is the least intrusive way to do
  it, so is likely to lead to more app usage, but on the other hand we mustn't
  make the cookie lifetime too long). And we definitely can't tell the same
  person across different devices.
* ...but all of that leaves scope for more mad science design in the future!

Do a brief introduction to Kafka
* why we want it
  * "let's just write to PG" -> and have the next service read from PG -> and
    gradually we get a spaghetti network of interconnected services, which is
    unmanagable
  * Instead, send all the data to Kafka and let each service consume what it
    wants

* Kafka itself
  * messages (events) are just bytes
  * producers and consumers
  * topics
  * *very brief* consideration of topics, mostly to showcase how consumers can
    share handling data between them if they want

Tiered storage
* this app is meant to run for a long time and be used worldwide, so a lot of
  data
* without tiered storage, data is kept on the service nodes - obvious
  diskspace limitations - more data = more cost for the service
* tiered storage moves older data to object storage, which is very cheap, but
  still accessible via Kafka (the only penalty is a little greater latency).
* so this is future-proofing the system
* note that this is a decision we took at the beginning of the system design,
  but it's OK to change a topic to tiered storage at a later time (you just
  can't change it back)

Briefly how the app works
* Summarise we're using fastapi and htmx - how much detail here? Probably nt
  much - refer to the repository.
* Explain our use of geoip2fast, and why we aren't transmitting IP addresses
  * Show the app code to get the location info
  * Mention that it can "fake" it if at localhost
* Briefly explain the use of cookies to keep state
* Because fastapi and asynchronous, we use aiokafka - also, it's one of the
  more "pythonic" Python Kafka libraries, which is nice
* Show the code to connect to a Producer
* Show the Event datastructure
* Show the code to send a message

Mention the "fake data" generator
* This is useful for testing
* Fake data has `cohort` set to `None` / `null` so we can distinguish it

Sending data to PG
* PG is always a good place to start :)
* Show the table (schema) in PG
* Apache Kafka Connect - another service - source and sink connectors
* The [JDBC
  sink](https://aiven.io/docs/products/kafka/kafka-connect/howto/jdbc-sink)
  is the generic connector to sink to databases.
      * Using the open source JDBC sink
      * Also works for other databases, including OpenSearch and MySQL
* Needs to specify the schema in each message
* Explain briefly how to set it up
  * Configuration file
  * Start service

Avro and why we use it
* compact
* the Confluent adaptation where the schema id goes on each message
* Karapace
* show the code to add the schema id to a message
* can I find Ryan's talk about working with schema changes in Avro streams?
  If so, link it

* The Karapace schema - or, more accurately, the JSON definition of the Avro
  schema which we are going to store in Karapace
  * show the code to register a schema?

Sending (the same) data to ClickHouse
* if we're mad data scientists, then we probably want our data in an
analytics database, and ClickHouse is a very good choice
* Luckily, there's an *integration* from Kafka to CH
  * Explain how an integration is different from a connector
* Aiven makes it easy to set up an integration, and doing so passes on
  information from the Kafka service to CH so we don't need to
* Show the configuration file

For extra credit, grumble about timestamp handling :)
* Obvious choices are Unix timestamp (in microseconds since the epoch) or an
  ISO 8601 string
* In either case, *use UTC*!
* PG natively would like an ISO 8601 string
  * but it's fairly easy to convert a Unix timestamp into an ISO 8601 string
* CH can't handle a full ISO 8601 string, but is very comfortable with Unix timestamps
  * and will *present* them as ISO 8601 strings for readability
* For analysis, timestamps probably win
* For compactness in messages, timestamps are definitely better

Round up:
* The GitHub repo has all the resources, and will grow over time
* The use of Kafka means that we can sink our data to different services as
  our needs evolve
* The use of tiered storage means we can afford to retain all of the data,
  which makes it easier to add new consumers and have them consume the
  lifetime of data
* There's scope for enriching the data into other topics
* There's scope for the app to write a different message format to other topics
  if that becomes necessary
* If we produce a new app, it too can write to the same topics (which the fake
  data generator demonstrates)
* Involving a schema safeguards us if (when) we need to change the message
  content
* Because Aiven has the service we need managed in the same environment, we
  get maximum convenience and control. But in the end, all the technology
  (services and connectors) we're using is open source.
* Go press buttons!


Other things we might talk about:
* The option to have a consumer read from the topic and write back altered
  data to another topic - for instance, to enrich the messages with location
  data.
* What other services can comsume Avro messages, and using connector or
  integration?
  * Consider
    * OpenSearch - the JDBC sink connector also uses Avro and Karapace
      (see [the
      docs](https://aiven.io/docs/products/kafka/kafka-connect/howto/opensearch-sink)
      and the article on [exploring Mastodon data](https://aiven.io/developer/mastodon-kafka-opensearch))
    * AlloyDB Omni if we want it's scalability and AI capabilities
    * Grafana?
* Remember Apache Kafka Connectors also let us connect to non-Aiven services -
  this is not a walled garden. The Aiven docs lists how to setup sink
  connectors for a variety of service.
* Consider using Grafana to monitor all the services
* Maybe show the console tools > data flow page, which shows services and how
  integrations link them (but not connectors)
