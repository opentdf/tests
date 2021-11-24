
## development

### environment variables
```shell
export KAS_PRIVATE_KEY=""
export EAS_CERTIFICATE=""
```

### server
```shell
pipenv install
pipenv run uvicorn main:app --reload --port 8000
```

### OpenAPI
```shell
pipenv run python3 main.py > openapi.json
```
