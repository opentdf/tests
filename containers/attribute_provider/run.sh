#!/bin/bash

export FLASK_APP=src/attribute_provider/app.py
export FLASK_ENV=development
pipenv run flask run --host 0.0.0.0
