# Behavior-Driven Development (BDD) Test Suite

This directory contains the Behavior-Driven Development (BDD) test suite for OpenTDF, which uses the `behave` framework. These tests are written in Gherkin syntax and are designed to be easily readable by both technical and non-technical stakeholders.

## Directory Structure

*   `features/`: This directory contains the feature files, which describe the behavior of the system in plain language.
    *   `*.feature`: These files contain the scenarios that are tested.
    *   `steps/`: This directory contains the Python code that implements the steps in the feature files.

*   `environment.py`: This file contains hooks that are run before and after tests, such as setting up and tearing down the test environment. It also handles the integration with the test framework, including the `ServiceLocator` and `EvidenceManager`.

## Running the BDD Tests

To run the BDD test suite, use the following command from the root of the `tests` directory:

```bash
behave bdd/
```

You can also run a specific feature file:

```bash
behave bdd/features/tdf_encryption.feature
```

The BDD tests are also integrated into the main CI/CD pipeline in the `.github/workflows/xtest.yml` file.
