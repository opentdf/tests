# Attribute Provider Web Service

Attribute Provider is a web service that works in conjunction with
our Identity Providier (IdP).  At today's writing, that IdP is
Keycloak.  Attribute Provider's role is as follows:

* Upon successful client authentication via Keycloak, Keycloak
  runs some custom Virtru-authored code that crafts a web
  service request to Attribute Provider.
* Attribute Provider processes the request, creates a Virtru
  Claims Object appropriate for that client in the current context,
  and returns it to our IdP/Keycloak.
* Our IdP/Keycloak then returns a signed JWT with the Claims Object
  inside.


## Build and Setup

Docker image names and version tags are set in `Makefile`.

### Build An Attribute Provider Docker Container

```
$ make
```

### Build A Docker Container, Push To Container Repo

```
$ make dockerbuildpush
```

### Build, Test, And Run A Local Attribute Provider Virtualenv

```
$ make localbuild
$ make test
$ make run
./run.sh
 * Serving Flask app 'src/attribute_provider/app.py' (lazy loading)
 * Environment: development
 * Debug mode: on
WARNING:werkzeug: * Running on all addresses.
   WARNING: This is a development server. Do not use it in a production deployment.
INFO:werkzeug: * Running on http://192.168.1.207:5000/ (Press CTRL+C to quit)
INFO:werkzeug: * Restarting with watchdog (fsevents)
 * Debugger is active!
 * Debugger PIN: 975-219-533
```

To test, in another terminal:

```
$ curl -XPOST -H 'Content-Type: application/json' \
  --data '{"client_id":"tdf", "client_pk": "aGVsbG8=", "token": {} }' \
  http://localhost:5000/
{
  "aliases": [],
  "attributes": [
    {
        "attribute": "https://example.com/attr/Classification/value/S"
    },
    {
        "attribute": "https://example.com/attr/COI/value/PRX"
    }
  ],
  "publicKey": "hello",
  "schemaVersion:": "1.2.3",
  "userId": "unknown"
}
```

In the flask app log, you should see:

```
DEBUG:attribute_provider.app:ImmutableMultiDict([])
DEBUG:attribute_provider.app:EnvironHeaders([('Host', 'localhost:5000'), ('User-Agent', 'curl/7.64.1'), ('Accept', '*/*'), ('Content-Type', 'application/json'), ('Content-Length', '60')])
DEBUG:attribute_provider.app:{'client_id': 'user1', 'client_pk': 'aGVsbG8=', 'token': {}}
DEBUG:attribute_provider.app:KEY: aGVsbG8=
DEBUG:attribute_provider.app:KEY: hello
DEBUG:attribute_provider.app:responding with: { 'aliases': [],
  'attributes': [ { 'obj': { 'attribute': 'https://example.com/attr/Classification/value/S'}},
                  { 'obj': { 'attribute': 'https://example.com/attr/COI/value/PRX'}}],
  'publicKey': 'hello',
  'schemaVersion:': '1.2.3',
  'userId': 'unknown'}
127.0.0.1 - - [12/May/2021 14:21:14] "POST / HTTP/1.1" 200 -
INFO:werkzeug:127.0.0.1 - - [12/May/2021 14:21:14] "POST / HTTP/1.1" 200 -
```
