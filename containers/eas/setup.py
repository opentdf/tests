"""Setup file."""

from setuptools import setup, find_packages

with open("VERSION", "r") as ver:
    version = ver.read().rstrip()

with open("README.md") as ld:
    LONG_DESCRIPTION = ld.read()

setup(
    name="eas",
    version=version,
    description="TDF3 AA proxy for Accounts",
    long_description=LONG_DESCRIPTION,
    keywords="TDF",
    url="https://github.com/virtru/etheria",
    license="UNLICENSED",
    platforms="Ubuntu",
    packages=find_packages(exclude=["ez_setup", "examples", "tests"]),
    py_modules=["wsgi"],
    include_package_data=True,
    data_files=[
        (
            "api",
            ["openapi.yaml"],
        ),
        (
            "config",
            [
                "config/attribute_urls.json",
                "config/defaults.json",
                "config/users.json",
                "config/users-pki.json",
            ],
        ),
        ("db", ["db/scripts/create_tables.sql", "db/scripts/drop_tables.sql"]),
    ],
    zip_safe=False,
    install_requires=[
        "Flask",
        "PyJWT==1.7.1",
        "connexion",
        "cryptography",
        "flask_cors",
        "gunicorn",
        "jsonschema",
        "requests",
        "swagger-ui-bundle",
        "wsgicors",
        "python-json-logger",
    ],
    classifiers=[
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Operating System :: POSIX",
    ],
)
