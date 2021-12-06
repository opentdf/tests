# TDF3 Entity Attribute Server

Reference example of a Trusted Data Format v3.0 (TDF3) Entity Attribute Service.

[Tdf3 Spec](https://github.com/virtru/tdf3-spec)

## Use

Note that all command lines below are run from working directory `eas`

### Quick start 1: Run the EAS in background

[Docker](https://docs.docker.com/) must be installed on your system.

**NOTE: It is suggested to use the docker-compose config in the root of this file via the `up_docker_compose.sh` to spin up all services**

Optionally you can use these steps to start the docker container.

```
# This pulls the latest python containers from docker hub. Should go fast
# unless your docker setup is way out of date.

docker pull python

# this command reads the Dockerfile to build a docker container called
# "eas". The build process copies the local directory into the container.
# IT also gets fresh copies of all the dependencies.
#
# If there are no changes to the source code this step goes fast.

docker build -t eas .

# this command runs the "Entity Access Server" with container port 4010 bound to localhost:4010

docker run -p 127.0.0.1:4010:4010 eas

# Both of these commands assume that docker is set up and heallthy on your machine
```

#### Run the unit tests (pytest)

On linux/mac:

```bash
cd ..
scripts/monotest eas cov
```

### Run or test the EAS server locally

[Python v3.7 or better](https://www.python.org/) must be installed on your system
with `pipenv`, e.g. via `pip install --user pipenv`.

- Auto-run the server. Run the start script in either environment. CTRL-C to stop. -`(.venv_xxx)...$ pipenv install && pipenv run ./scripts/start \<optional port number, defaults to 4010\>`

- Auto-Run the tests. In the test environment, run the test script. This leaves `ptw` running which will monitor changes and rerun tests on change. Press CTRL-C to stop. -`(.venv_test)...$ pipenv install --dev && pipenv run ./scripts/test \<optional test file path\>`

- Get a code coverage report. In the test environment, run: -`(.venv_test)...$ pipenv install --dev && scripts/coverage`

- At the end of the session, deactivate the environment. Optionally, just close the window. -`$(.venv-test) deactivate` -`$ exit`

### Read/Edit the API definitions

[Docker](https://docs.docker.com/) must be installed on your system.

- Start or stop the API editor. It runs in a docker container in the background: -`$ ./scripts/start\_api\_editor` -`$ ./scripts/stop\_api\_editor`

- Access the editor in a browser at **localhost:80**
  -Open file "swagger.yaml"

## Configuration

The [EASConfig class](src/eas_config.py) class controls configuration items. It will attempt the follow actions, in order, to load each configuration item:

1 Load setting from system environment variable.
2 Load default, if any, from defaults.json file.

If all three methods fail, an error is logged.

Once a configuration item is loaded the first time, it is saved in a runtime cache in the EAS instance.

When deployed, environment variables are normally set using `docker-compose.yml` or other methods appropriate to the deployment environment. See the [root README](../README.md)

### Required

See the [root README](../README.md) for instructions on generating keys for EAS and KAS. Keys are required for EAS to operate. Each of the following environment variables must contain a path to the corresponding key:

- EAS_CERTIFICATE
  - PEM data for EAS
- EAS_PRIVATE_KEY
  - (SECRET) Private key EAS uses to certify responses.
- KAS_CERTIFICATE
  - PEM data for default KAS public key used to validate responses

### Optional

Defaults set in [config/defaults.json](config/defaults.json) for the following configuration items:

- EAS_ENTITY_ID_HEADER
  - Set to use a request header to set Entity Id.
  - Example value: HTTP_X_FORWARDED_CLIENT_DN
- DEFAULT_ATTRIBUTE_URL
  - Every Entity will be assigned, at minimum, this default attribute.
- KAS_DEFAULT_URL
  - KAS server to use in coordination with this EAS
- EAS_ENTITY_EXPIRATION
  - Lifetime of the token that EAS issues to certify an Entity, like a user or device. When expired, the entity must authenticate to EAS again. Use: "exp_days", "exp_hrs", "exp_mins" or "exp_sec".
- LOGLEVEL
  - EAS logging level. Use a Python Logging level: ""DEBUG", "INFO", "WARNING", "ERROR", or "CRITICAL".
  - DEBUG is not recommended for production and may log user data.
- SWAGGER_UI
  - "False" or "0" to disable Swagger UI from being served by EAS. Default is to enable Swagger UI and make available on `/ui` path.
- EAS_SERVICE_TYPE
  - Default: `SQL` to select the SQL Lite data persistence.
  - If you have extended EAS with other service implementations, enter them here 
- EAS_DB_PATH
  - Path to the SQLite database.
  - Only relevant when EAS_SERVICE_TYPE="SQL". There should be a valid database or a zero byte file at this location (App will create tables).
  - Defaults to relative path "db/data/eas_database.sqlite". When deploying, use EAS_DB_PATH environment variable to override.
- EAS_USERS_JSON
  - Path to json document containing initial users to load on startup (loads if not already created).

### Cross-Origin Resource Sharing (CORS) settings

- WSGI_CORS_HEADERS (Default: "Origin, X-Requested-With, Content-Type, Authorization, X-Session-Id, X-Virtru-Client, X-No-Redirect")
- WSGI_CORS_METHODS (Default: "GET, POST, PUT, PATCH, OPTIONS, DELETE")
- WSGI_CORS_MAX_AGE (Default: 180)
- WSGI_CORS_ORIGIN (Default: "https://localhost")

### Security headers
reference: https://flask.palletsprojects.com/en/master/security/#security-headers

- X-Content-Type-Options 
  - Anti-MIME-Sniffing header
- X-Frame-Options
  - Prevents external sites from embedding your site in an iframe.

### Logging

Currently, the application uses two loggers:
- The preferred mechanism is Flask logging (`app.logger` or `current_app.logger`) 
- Where the Flask logger is unreachable (e.g. during startup) EAS uses vanilla Python logging (`import logger`). 
This is also used in some libraries, and in some code that hasn't yet been updated.

## Architecture and Code Organization

EAS is a Python [Flask](https://flask.palletsprojects.com/) application that is run in a [Gunicorn](https://gunicorn.org/) WSGI Web Server

### Architecture - OpenAPI and Connexion layer
The REST API - endpoints, requirements for requests and responses, and schemas - 
are defined as an [OpenAPI 3](https://swagger.io/specification/) specification in the file [openapi.yaml](openapi.yaml)

EAS uses the Python [Connexion framework](https://connexion.readthedocs.io/en/latest/) to generate a Flask app from the OpenAPI spec. 
Each endpoint/method in openapi.yaml has an operationId to route it to Python code, for example:

```yaml
operationId: src.web.attribute_name.get
```

Connexion validates all requests and responses against the OpenAPI specification.

OpenAPI has a rich set of tools from [SMARTBEAR](https://swagger.io/) and [many others](https://openapi.tools/). 
For example, the ABACUS front end leverages the API definitions to interface with EAS. 
Our CI tooling includes OWASP ZAP security scans which use the OpenAPI spec as a starting point.  

### Architecture - Web module layer

The example above corresponds to the get() method in the [attribute_name](src/web/attribute_name.py) module in the web directory:

```python
@statusify
def get(name: str = None, namespace: str = None):
    """Retrieve an attribute name."""
    attr_name_svc = attr_name_service()
    return attr_name_svc.get(namespace, name)
```

The inputs defined in the OpenAPI become the parameters in this function call.  
For POST, etc. the request body becomes the `body` parameter.

The web methods like get() above call the services layer to get the work done.

The `@statusify` decorator handles status codes, headers, and errors. 
Errors raised by the services become the appropriate http error codes with a standardized response body containing details. 

### Architecture - Services layer

The Services layer is the Python code that gets the work done. This code is in the [services](src/services) directory.

Most services have an abstract Class that defines the inputs and outputs.  This allows for multiple implementations 
of the data layer.

The concrete classes implement the abstract classes. They work with Models objects and encapsulate all interactions 
with the Data layer.

### Architecture - Models objects

The classes in the [models](src/models) directory are the business models for the objects EAS works with.  
Generally they will have a `to_raw_dict()` and `from_raw_dict()` method to convert them to plain Python dicts 
to support serializing/deserializing to and from JSON, and which must match the schemas defined in OpenAPI.
These models perform validation on the objects and support the creation and decomposition of the attribute URIs.

### Architecture - Data layer

The "SQL" type services, in the [services/sql](src/services/sql) directory, support a basic SQLite 3 
relational database. [sqlite_connector.py](src/db_connectors/sqlite_connector.py) manages the db location, 
the creation of tables, and the running of SQL code. The database interactions are standard SQL but 
the Platform team is also exploring ORM options. 
The table creation SQL (or DDL) is in [create_tables.sql](db/scripts/create_tables.sql).

The "MEM" (in memory Python objects) implementation has been removed and is no longer supported.  
SQLite has proven to be sufficiently lightweight.

The services architecture is designed to support future persistence models. For example, 
enterprise relational databases, NoSQL databases, or enterprise identity management software.  

## OpenAPI

[OpenAPI](openapi.yaml) is the server's contract with its clients.
All requests and responses are validated against this specifiction.

### Client Generation
reference: https://openapi-generator.tech/

To create a Python client, run the following:
```shell script
docker run --rm \
  -v ${PWD}:/local/ \
  openapitools/openapi-generator-cli \
    generate \
      -i /local/openapi.yaml \
      -g python \
      -o /local/out/ \
      --additional-properties generateSourceCodeOnly=true
```

### Deprecated

#### Path /user
Replaced by /entity

#### Path /attribute
Replaced by /attr 