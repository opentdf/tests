# TDF3 Key Access Server Core Package

The KAS core code implements the TDF3 standard in an open way. To create a KAS, import this dependency into your KAS server, configure it on boot-up, and run your server. The KAS core is a Flask app that should be run in GreenUnicorn or some other service manager.

## Use

The KAS core code has not been released and is not yet available on PyPI. Explore the script files in [etheria](https://github.com/opentdf/backendd) for examples of how to import the repo from git.

The KAS class is a builder for a [WSGI-compliant](https://en.wikipedia.org/wiki/Web_Server_Gateway_Interface) [Flask app](http://flask.pocoo.org/) that implements the TDF3 KAS protocol. Construct a Kas instance, configure it, and have it build the app:

```python
from tdf3_kas_core import Kas

def make_my_kas_app(name):
	"""Construct a KAS as a Flask app."""

	# The Kas constructor takes one argument, the python __name__ parameter of the file
	# calling this function.  Typically this will be "__main__"
	kas = Kas(name)

	# The Kas produces version info as its response to calles to the default endpoint "/"
	kas.version('2.3.0')

	# Set the attribute policies. These are the rules the KAS uses to decide access.
	# Three kinds are currently supported: "allOf", "anyOf", and "hierarchy."  The
	# attribute URI string is the key; an options object is the value.
	kas.set_attribute_config({
	  "https://aa.virtru.com/attr/unique-identifier": { "rule": "allOf" },
	  "https://aa.virtru.com/attr/primary-organization": { "rule": "allOf" },
	  "https://example.com/attr/Classification": {
	      "rule": "hierarchy",
	      "order": ["TS", "S", "C", "U"]
	  },
	  "https://example.com/attr/Rel": { "rule": "anyOf" },
	  "https://example.com/attr/NTK": { "rule": "allOf" },
	  "https://example.com/attr/COI": { "rule": "allOf" }
	}}

	# Three RSA keys must be set: "KAS_PRIVATE", "KAS_PUBLIC", and "AA_PUBLIC".
	# The recommended size for these keys is 2048 or better. Indicate whether they are
	# "PUBLIC" or "PRIVATE" with the second argument.

	# The keys can be set indirectly with paths to files containing the keys:
	kas.set_key_path("KAS-PRIVATE", "PRIVATE", "/path/to/my/key/stash/kas_private.pem")
	kas.set_key_path("KAS-PUBLIC", "PUBLIC", "/path/to/my/key/stash/kas_public.pem")

	# or directly using PEM strings:
	kas.set_key_pem("AA-PUBLIC", "PUBLIC", "-----BEGIN PUBLIC KEY-----/nMIIBIjANBgkqhk... ")

	# The KAS core accepts two kinds of plugins, upsert and rewrap.  Upsert
	# plugins are used to create and update policies on back-end systems. They
	# must extend the "AbstractUpsertPlugin" class:
	#
	# from tdf3_kas_core import AbstractUpsertPlugin
	#
	# class MyUpsertPlugin(AbstractUpsertPlugin):
	#	...
	#
	kas.use_upsert_plugin(MyUpsertPlugin())

	# Rewrap plugins are called as part of the key rewrap process; they must extend
	# the "AbstractRewrapPlugin" class:
	#
	# from tdf3_kas_core import AbstractRewrapPlugin
	#
	# class MyRewrapPlugin(AbstractRewrapPlugin):
	#	...
	#
	kas.use_rewrap_plugin(MyRewrapPlugin())

	# Any number plugins can be loaded.  They will run sequentially within their
	# respective stacks in the order in which they were loaded:
	kas.use_upsert_plugin(MyOtherUpsertPlugin())
	kas.use_rewrap_plugin(MySecondRewrapPlugin())
	kas.use_rewrap_plugin(MyThirdRewrapPlugin())

	# Finally, have the Kas instance generate the Flask app.
	return kas.app()

```


### Publishing tdf3_kas_core

We publish to a private PyPI managed by a Sonatype Nexus Repository Manager.
This is at https://hub.nexus.virtru.com/. 
To get user creds, you'll need to follow [the guide in our devops wiki](https://virtru.atlassian.net/wiki/spaces/ENG/pages/707788811/Getting+Started+With+Hub+Nexus).


1. Use aviatrix to connect to the virtru VPN named `virtru-us-west-2`
2. Run the following script:

```sh
pipenv install --dev
pipenv run python3 -m build

TWINE_REPOSITORY_URL="https://nexus.hub.virtru.com/repository/pypi-private/" \
TWINE_USERNAME=_DTGU7S2 \
SOURCE_DATE_EPOCH=$(git show -s --format=%ct) \
pipenv run python3 -m twine upload dist/*
```

### Consuming this package

In your `Pipfile`
([source])(https://pipenv-fork.readthedocs.io/en/latest/advanced.html#specifying-package-indexes)) :

```
[[source]]
url = "https://pypi.org/simple"
verify_ssl = true
name = "pypi"

[[source]]
url = "https://nexus.hub.virtru.com/repository/pypi-private/simple"
verify_ssl = true
name = "virtru-pypi-private"

[packages]
tdf3-kas-core = {version="*", index="virtru-pypi-private"}
```

You'll also need some creds!

Note that if you've already installed the library in another way, you may need to clean out the old one.
For example, run `pipenv lock --clear && pipenv clean` if you are using Pipfiles.
