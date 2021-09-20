"""The setup.py for TDF3-kas-oss."""

from setuptools import setup, find_packages

with open("VERSION", "r") as ver:
    version = ver.read().rstrip()

with open("README.md", "r") as readme:
    long_description = readme.read()

setup(
    name="tdf3-kas-oss",
    version=version,
    description="TDF3 KAS OSS - Setup for open source software",
    long_description=long_description,
    keywords="TDF",
    author="Virtru Corporation",
    author_email="support@virtru.com",
    url="https://github.com/virtru/etheria",
    license="ISC",
    platforms="Ubuntu",
    packages=find_packages(exclude=["scripts"]),
    py_modules=["wsgi"],
    include_package_data=True,
    data_files=[("config", ["config/attribute-config.json"])],
    zip_safe=False,
    install_requires=[
        "gunicorn",
        "requests",
        "python-json-logger",
        "wsgicors",
    ],
    entry_points={"console_scripts": ["kas = wsgi:app"]},
    classifiers=[
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Operating System :: POSIX",
    ],
)
