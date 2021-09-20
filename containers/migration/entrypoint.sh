#!/bin/bash

set -e

DATABASE_URL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@$POSTGRES_HOST/$POSTGRES_DATABASE"
sed -i -e "s|^sqlalchemy.url = .*$|sqlalchemy.url = $DATABASE_URL|" alembic.ini

until pg_isready --host=$POSTGRES_HOST --port=$POSTGRES_PORT --dbname=$POSTGRES_DB --username $POSTGRES_USER --timeout=0; do
  sleep 0.2
done

echo "alembic"
alembic --raiseerr -c alembic.ini current

echo "creating database roles"
psql $DATABASE_URL -f migration/schema.sql
