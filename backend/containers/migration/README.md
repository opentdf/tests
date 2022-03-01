## Development

### Start database

```shell
mkdir -p data
docker run \
    --detach \
    --publish 0.0.0.0:5432:5432 \
    --volume data:/var/lib/postgresql/data \
    --env POSTGRES_PASSWORD=myPostgresPassword \
    --env PGDATA=/var/lib/postgresql/data/pgdata \
    postgres
```

### Initialize schema

```shell
psql \
   --host=localhost \
   --port=5432 \
   --username=postgres \
   --dbname=postgres \
   --command='create database tdf_database;'
#   myPostgresPassword

psql \
   --host=localhost \
   --port=5432 \
   --username=postgres \
   --dbname=tdf_database \
   --file=containers/migration/schema.sql

#   myPostgresPassword
```

### Migration

https://github.com/JeffGradyAtVirtru/python-example
