# Remote Payload
Provides temporary credentials to upload a file to a S3 service.
Dictates where to upload, access control, and establishes constraints.

## Development

### environment variables
```shell
export BUCKET=datalake
export AWS_ACCESS_KEY_ID=AKI...
export AWS_SECRET_ACCESS_KEY=2Y...
export AWS_DEFAULT_REGION=us-west-2
export CORS_ORIGINS="localhost,etheria.local"
```

### server
```shell
pipenv install
pipenv run uvicorn main:app --reload --port 4050
```

### OpenAPI
```shell
pipenv run python3 main.py > openapi.json
```


## Kubernetes

### image
```shell
# from project root
TAG=`python3 -c "import storage;print(storage.__version__)"`
docker build --no-cache --tag opentdf/storage:${TAG} storage
```

### secrets
deployment.envFrom.secretRef == tdf-storage-secrets
```shell
kubectl create secret generic tdf-storage-secrets \
  --from-literal=AWS_ACCESS_KEY_ID=myAccessKeyId \
  --from-literal=AWS_SECRET_ACCESS_KEY=mySecretAccessKey
```

### helm
```shell
# from project root
helm upgrade --install --values deployments/local/values-tdf-storage-service.yaml tdf-storage-service ./charts/storage --debug
```
Then follow the `NOTES:`

## Troubleshooting

If the S3 upload service returns `The bucket you are attempting to access must be addressed using the specified endpoint`
Then specify the region `AWS_DEFAULT_REGION=us-west-2` of the bucket on the container

For debugging S3 federated token, use the created credentials to ENV VAR including `export AWS_SESSION_TOKEN=`
