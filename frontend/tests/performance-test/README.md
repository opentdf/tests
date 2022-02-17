# Performance test kas/eas using tdf3sdk.

## Setup

```
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
export EAS_ENDPOINT=http://local.virtru.com/eas
```

OR run

```shell script
export EAS_ENDPOINT=http://local.virtru.com/eas
source run_get_time.sh
```

## Run

`EAS_ENDPOINT` environment variable should be specified

python get_time.py [<file_path>]

#### Arguments:

- file*path *(optional, default: ./performance-run-result.json)\_: where to place json output

## Output

Output in json format:

```json
{
  "encrypt_time": "<encrypt time per call>",
  "decrypt_time": "<decrypt time per call>"
}
```

## docker-compose
```shell script
docker-compose up --build --exit-code-from performance-test performance-test
docker-compose logs
docker-compose down
```

## K6
reference: https://github.com/loadimpact/k6

### local development testing
```shell script
brew install k6
# EAS
k6 run --vus 10 --iterations 10 performance-test/eas/script.js
# KAS
k6 run --vus 10 --iterations 10 performance-test/kas/script.js
```

### Docker
To be used in a CI
```shell script
docker pull loadimpact/k6

docker run -i loadimpact/k6 run - <script.js
```

### OpenAPI generate for python
reference: https://github.com/triaxtec/openapi-python-client

```shell
openapi-python-client update --url http://pflynn.local:4030/openapi.json
```

### OpenAPI generate for K6 (beta)
reference: https://openapi-generator.tech/

Generate a performance client code.  
The code generated requires modification to run.
If openapi.yml changes, run command below, and merge changes.

#### EAS
```shell script
# run from project root
docker run --rm \
  -v ${PWD}:/local/ \
  openapitools/openapi-generator-cli \
    generate \
      -i /local/eas/openapi.yaml \
      -g k6 \
      -o /local/performance-test/eas/ \
      --additional-properties ensureUniqueParams=true
```
#### KAS
https://openapi-generator.tech/
```shell script
# run from project root
docker run --rm \
  -v ${PWD}:/local/ \
  openapitools/openapi-generator-cli \
    generate \
      -i /local/kas_core/api/openapi.yaml \
      -g k6 \
      -o /local/performance-test/kas/ \
      --additional-properties ensureUniqueParams=true
```

