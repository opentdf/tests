# OpenTDF Tests

This repository contains the test suites for the OpenTDF (Trusted Data Format) platform. The primary goal of these tests is to ensure the quality, reliability, and security of the OpenTDF platform and its associated SDKs.

## Test Suites

This repository contains several test suites, each with a different focus:

*   **[xtest](xtest/README.md)**: The cross-SDK compatibility test suite. This is the main test suite for verifying that the Go, Java, and JavaScript SDKs can interoperate correctly.
*   **[bdd](bdd/README.md)**: The Behavior-Driven Development (BDD) test suite. These tests are written in Gherkin syntax and are designed to be easily readable by both technical and non-technical stakeholders.
*   **[vulnerability](vulnerability/README.md)**: The vulnerability test suite. These tests use Playwright to automate checks for vulnerabilities identified during penetration testing.

## The One Script to Rule Them All

To simplify the process of running the tests, this repository provides a single Python script, `run.py`, that can be used to set up the environment, start the platform, run the tests, and stop the platform.

### Prerequisites

Before running the script, you must have the following tools installed:

*   Python 3.13+
*   `uv` (can be installed with `pip install uv`)
*   Docker and Docker Compose
*   Node.js 22+
*   Java 17+
*   Maven
*   Go 1.24+

### Usage

The `run.py` script has the following commands:

*   `setup`: Sets up the test environment by creating a virtual environment, installing dependencies from `requirements.txt`, and checking out the necessary SDKs.
*   `start`: Starts the OpenTDF platform using Docker Compose.
*   `stop`: Stops the OpenTDF platform.
*   `test`: Runs the specified test suite within the virtual environment.

**Examples:**

To set up the environment, start the platform, run all the tests, and then stop the platform, you would run the following commands:

```bash
python3 run.py setup
python3 run.py start
python3 run.py test
python3 run.py stop
```

To run a specific test suite, such as the `xtest` suite with the `no-kas` profile, you would run:

```bash
python3 run.py test --suite xtest --profile no-kas
```

For more information on the available options, run:

```bash
python3 run.py --help
python3 run.py test --help
```

## Manual Setup

For more granular control over the test environment, you can set up the virtual environment and install dependencies manually.

### Creating the Virtual Environment

To create the virtual environment, run the following command from the root of the `tests` directory:

```bash
uv venv --python python3.13
```

This will create a new virtual environment in the `.venv` directory.

### Activating the Virtual Environment

To activate the virtual environment, run the following command:

```bash
source .venv/bin/activate
```

### Installing Dependencies

To install the dependencies from the `requirements.txt` lock file, run the following command:

```bash
uv pip sync requirements.txt
```

## Test Framework

This repository also contains a modern test framework, located in the `framework` directory. The framework provides a set of tools and libraries for building robust, reliable, and maintainable test suites. For more information, please see the [framework/README.md](framework/README.md) file.
