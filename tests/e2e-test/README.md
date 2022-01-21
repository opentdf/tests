# End-to-end test

Cloned https://github.com/virtru/tdf3-py-e2e
Made for preventing from breaking python core sdk(https://pypi.org/project/tdf3sdk/) EAS interactions this e2e scrypt was created.

## Running Tests locally

1. Run EAS microservices locally
2. Run individual service_*.  See corresponding README.md

## Stress Tests

Runs by default with e2e tests, statistics can be found in `graph` folder, generated after test passed. File `run_test_py` can be runned without shell script (if all dependecies installed) like:

`python3 run_test.py --size=10 --step-1` where size is maximum size of file for test and step is increment for its size

Or `python3 run_test.py --stress=False` to ignore stress test and run only e2e

Setup and run shell script runs it with default params

`--stress=True --size=10 --step=1`

### Environment variables
```shell
export KAS_HOST=http://localhost:8000
export ENTITY_OBJECT_HOST=http://localhost:4010
export ATTRIBUTE_AUTHORITY_HOST=http://localhost:4020
export ENTITLEMENT_HOST=http://localhost:4030
export ENTITY_HOST=http://localhost:4040
```

```shell
pip3 install tdf3sdk=="$sdkVersion"
pip3 install -r requirements.txt
python3 run_test.py
```

## docker-compose
```shell script
docker-compose --env-file certs/.env --file e2e-test/docker-compose.yml up --build --exit-code-from e2e-test e2e-test
docker-compose --env-file certs/.env --file e2e-test/docker-compose.yml down --rmi=local
```
