# Getting Started with Terraform using our Button App

<!--toc:start-->

- [How to create the button app services in terraform](#how-to-create-the-button-app-services-in-terraform)
  - [Ignore build files](#ignore-build-files)
  - [Creating our Variables](#creating-our-variables)
  - [Deploying our Infrastructure](#deploying-our-infrastructure) - [Initialize Services](#initialize-services) - [Plan Services](#plan-services) - [Apply Services](#apply-services)
  <!--toc:end-->

One of the easiest ways to deploy several services, especially if you intend to use these services together is to use [Terraform](https://registry.terraform.io/).

Terraform is a popular infrastructure-as-code (IAC) tool that gives you the ability to provide information about a deployment and deploy your services in a consistent manner from the command line.

Aiven offers the [Aiven Provider for Terraform](https://registry.terraform.io/providers/aiven/aiven/latest/docs) which includes resources and data configurations for your deployment.

This guide walks through using Terraform with Aiven and is perfect if you are using Terraform for the first time.

> [!NOTE]
> TLDR: This is a walkthrough on how to setup your Aiven services using terraform. It breaks down the terraform files that were created. If you want to know how to build the services with the included files, skip to the [Apply Services](#apply-services) section or view the README.

## Our Terraform Layout

```
terraform
├── aiven.tf
├── clickhouse.tf
├── kafka.tf
├── postgres.tf
└── variables.tf
```

We put all our files in a `terraform` folder to contain the files that are created when you start building your services. This means that if we want to build the our configuration we either need to run our commands from the `terraform` directory or apply the `-chdir=terraform` command.

> [!NOTE]
> For this post we will assume that all commands are ran from the `terraform` directory

## Ignoring build files

Once you initialize and build your services, it will create some files that are used to cache information about your deployment.
a
Having these files in source control can cause issues (and excessive changes) if multiple people are using the same repo.

To ignore these files, add the following lines to your `.gitignore`:

```shell
echo terraform/.terraform >> .gitignore
echo terraform/.terraform.lock.hcl >> .gitignore
echo terraform/terraform.tfstate.backup >> .gitignore
echo terraform/terraform.tfstate >> .gitignore
```

## Creating our Variables and consistency

The goal with infrastructure as code (IAC) tools like terraform is to simplify the process of creating and deploying our services in difference instances and services.

We can create variables that make our setup flexible but still consistent. For example, your team uses different clouds/regions for testing vs prod.

We can keep our code consistent and make the cloud name a variable and then provide it at runtime.

### variables

We need to define our terraform files with in a `variables.tf` file. This allows us to use them across all of our services.

```terraform
# This is a snippet of terraform/variables.tf

variable "aiven_api_token" {
  description = "The api token for the aiven service"
  type        = string
}

variable "aiven_project_name" {
  description = "The aiven project"
  type        = string
}

variable "cloud_name" {
  description = "The cloud provider and region for Aiven services. Example: google-us-east1"
  type        = string
}
```

Now we can apply these variables in our terraform code.

```terraform
# snippet from terraform/aiven.tf

provider "aiven" {
  api_token = var.aiven_api_token
}

data "aiven_project" "button_app" {
  project = var.aiven_project_name
}

```

### Adding your variables

We've talked about how we setup Terraform to use variables, but how do we supply values for these variables?

The first instance is you can add a `default` parameter in the variables. This is great for values that you would normally have set but want to offer the ability to change the value easily.

The other option is to add a `terraform.tfvars` file which you can supply values in a single file.

> [!Warning]
> Be sure not to expose secrets by loading files like these into source control.

Lastly, you can provide the variables when you apply your configuration and build your services.

```shell
terraform apply -var 'cloud_name=aws-us-east1'
```

### Consistency with a common implementation string (using random)

In this project we're creating multiple services and we would want to make sure that we know which services are connected to one another.

Aiven's platform allows for multiple projects but we may want to have all our versions in one project.

We can also use other aiven features like adding tags, but we can use [terraforms `random` provider](https://registry.terraform.io/providers/hashicorp/random/latest/docs) to create a random suffix and apply it to all our services. This allows us to have multiple versions of the project within one Aiven project and quickly identify with services are connected to one another.

In your top level service (for us it's `terraform/aiven.tf`), add the `random_sting` provider for a string that is 6 characters, all lowercase, and with no special characters.

```terraform
resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}
```

We can include our `suffix` fragments in strings. In the sample below, we can hard-code the base name of the service name and then append our suffix to the end.

```terraform
# from terraform/kafka.tf

resource "aiven_kafka" "kafka_button_app" {
  project      = data.aiven_project.button_app.project
  service_name = "kafka-button-app-${random_string.suffix.result}"
```

If we do this for all of our services we can easily identify services in the project with that lookup. Aiven recommends using [JQ](https://jqlang.org/) with the aiven command line [avn](https://github.com/aiven/aiven-client).

```shell
$ echo 'With the Suffix = "4sxejq"'

$ avn service list --json | jq '.[] | select(.service_name | endswith("4sxejq")) | .service_name'

"ch-button-app-4sxejq"
"kafka-button-app-4sxejq"
"pg-button-app-4sxejq"
```

## Creating our Infrastructure

Let's walk through the files of our infrastructure.

### Base Infrastructure

We will start with our `aiven.tf`. This is where we will define the terraform spec and supply our `required_version` and `required_providers`. This adds the providers that we'll use in this deployment as dependencies. We'll want the `hashicorp/random` and the `aiven` providers.

We've talked about the code for both of these providers in the section above. We use `provider` to assign configurations that will be used across the `aiven` provider. To retrieve information (and prevent it from being changed) we will use `data`. This allows us to fetch the project we supply in the `aiven_project_name` variable.

### Service Files

Starting with our `clickhouse.tf` and `postgres.tf`, we will create a simple configuration for these services. The beauty of terraform is that we can add more settings as we find it necessary and it will only adjust the settings when needed, without having to delete data and destroy your service.

> [!NOTE]
> There are some commands that, due to their nature are destructive but this would be the case whether using Terraform or not.

We create these services using `resource` and supply the `project`, `cloud_name`, `plan`, and `service_name`. Reminder that we use the `random_string` resource to make sure the files all have the same suffix.

```terraform
# postgres.tf
resource "aiven_pg" "pg_button_app" {
  project      = data.aiven_project.button_app.project
  cloud_name   = var.cloud_name
  plan         = "hobbyist"
  service_name = "pg-button-app-${random_string.suffix.result}"
}
```

Our Aiven for Clickhouse configuration is similar with the only addition of creating an output that will be displayed after the file is created. This also allows us to store that information as a variable.

```terraform
# clickhouse.tf
# top portion is similar to postgres.tf

output "clickhouse_service_name" {
  value = aiven_clickhouse.ch_button_app.service_name
}
```

This means instead of using `avn` and JQ or memorizing the service name you can ask for terraform's output which can be passed into a .env file and used elsewhere.

```shell
$ terraform output
clickhouse_service_name = "ch-button-app-4sxejq"
kafka_service_name = "kafka-button-app-4sxejq"
```

> [!NOTE]
> Some values are protected by secrets. You will need to use `sensitive=true` and you will need to use `-json` to show those values.

The last service file really shows the strength of infrastructure-as-code. `kafka.tf` does all of the things seen in the previous service files, but also sets values for settings in our Kafka cluster. Some settings have there own sections so it's important to check out the [docs](https://registry.terraform.io/providers/aiven/aiven/latest/docs/resources/kafka) for support.

In our sample we do the following:

- enable REST API access, kafka connection support, schema registry and management with Karapace, tiered-storage, and what services have public access.
- we set values like the `kafka_version`,`group_max_session_timeout_ms`, `auto_create_topics_enable`, and `log_retention_bytes`

```terraform
# kafka.tf
# top section like other service files

  kafka_user_config {
    kafka_rest      = true
    kafka_connect   = true
    schema_registry = true
    kafka_version   = "3.8"

    tiered_storage {
      enabled = true
    }

    kafka {
      group_max_session_timeout_ms = 70000
      log_retention_bytes          = 1000000000
      auto_create_topics_enable    = true
    }

    public_access {
      kafka_rest    = true
      kafka_connect = true
    }
  }

```

We can also create our topic for our web app and configure it as well.

```terraform
resource "aiven_kafka_topic" "button_app" {
  project                = data.aiven_project.button_app.project
  service_name           = aiven_kafka.kafka_button_app.service_name
  topic_name             = "button_presses"
  partitions             = 3
  replication            = 2
  termination_protection = true

  config {
    cleanup_policy        = "delete"
    remote_storage_enable = true
    local_retention_ms    = 30000
  }

  timeouts {
    create = "1m"
    read   = "5m"
  }
}
```

This ensures that our topics are configured correctly. This is important as settings around `timeouts`, `local_retention_ms`, and `cleanup_policy`, can have an effect on tiered-storage usage and performance.

### Combatting Terraform overwhelm

Terraform setups can feel a little overwhelming. My suggestion is to create a base setup that your team can agree on and always use those settings as a template. You can use variables with defaults to help with this. Doing this will narrow your focus to fewer files and will make documenting your Infrastructure easier.

## Deploying our Infrastructure

### Initialize Services

### Plan Services

### Apply Services

Now that the services are built we can run our command

```

```
