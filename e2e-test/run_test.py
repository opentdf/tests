import logging
import os
import random
import re
import shutil
import string
import sys
import timeit

import click
import matplotlib.pyplot as plt
import requests
from tdf3sdk import TDF3Client, LogLevel


def test_setup():
    # create attribute
    attribute_authority_host = os.environ["ATTRIBUTE_AUTHORITY_HOST"]
    response = requests.post(
        f"{attribute_authority_host}/v1/authorityNamespace",
        params={"request_authority_namespace": "https://eas.local"},
    )
    if response.status_code != 200:
        print(response.text)
        exit(1)
    response = requests.post(
        f"{attribute_authority_host}/v1/attr",
        json={
            "authorityNamespace": "https://eas.local",
            "name": "language",
            "rule": "anyOf",
            "state": "published",
            "order": ["urdu", "french", "japanese", "german"],
        },
    )
    if response.status_code != 200:
        print(response.text)
        exit(1)
    # create entity
    entity_host = os.environ["ENTITY_HOST"]
    response = requests.post(
        f"{entity_host}/v1/entity",
        json={
            "userId": "Charlie_1234",
            "email": "charlie@eas.local",
            "name": "Charlie",
            "nonPersonEntity": False,
        },
    )
    if response.status_code != 200:
        print(response.text)
        exit(1)
    # entitlement
    entitlement_host = os.environ["ENTITLEMENT_HOST"]
    entity_id = "Charlie_1234"
    response = requests.put(
        f"{entitlement_host}/v1/entity/{entity_id}/attribute",
        json=["https://eas.local/attr/language/value/urdu"],
    )
    if response.status_code != 200:
        print(response.text)
        exit(1)


# Command line arguments.
@click.command()
@click.option(
    "--stress",
    "-st",
    is_flag=True,
    default=True,
    help="Perform the stress/performance tests.",
)
@click.option(
    "--size", default=100, help="Generate files up to given size (MB).", type=int
)
@click.option(
    "--step", default=10, help="Generate files with given increment (MB).", type=int
)
def main(stress, size, step):
    try:
        test_setup()
        file_api_runner = FileApiTestRunner()
        data_api_runner = DataApiTestRunner()

        file_api_runner.run()
        data_api_runner.run()

        if stress:
            stress_test_runner = StressTestRunner(size, step)
            stress_test_runner.run()

    except Exception as e:
        print(e)
        print("Unexpected error: %s" % sys.exc_info()[0])
        raise

    exit(0)


class Assert:
    def __init__(self):
        self.logger = logging.getLogger(LOGGER_NAME)

    def assert_fail(self, action, *args):
        try:
            action(*args)
        except Exception as e:
            print(e)
            return True
        else:
            self.logger.error("Error: Exception should have happen")
            return False

    def assert_pass(self, action, *args):
        try:
            action(*args)
        except Exception as e:
            print(e)
            exc_info = sys.exc_info()
            self.logger.error(f"Error: Exception :{exc_info}")
            return False
        else:
            return True

    def print_result(self, result, test_name):
        # https: // pypi.org / project / colorama /

        if result:
            self.logger.info(f"PASS: {test_name}")
        else:
            self.logger.error(f"FAIL: {test_name}")
            exit(1)


class DataApiTestRunner(Assert):
    def run(self):
        self.logger.info(f"******************* Testing Data Api encrypt-decrypt ******")

        self.print_result(
            self.assert_pass(DataApiTestRunner.encrypt_decrypt, ""),
            "Encryption and decryption should successfully passed",
        )
        self.print_result(
            self.assert_pass(DataApiTestRunner.check_data_is_valid),
            "Decrypted data should match original",
        )

    @staticmethod
    def encrypt_decrypt(origin):
        client = TDF3Client(
            eas_url=os.environ["ENTITY_OBJECT_HOST"], user="Charlie_1234"
        )
        client.enable_console_logging(LogLevel.Info)
        client.with_data_attributes(["https://eas.local/attr/language/value/urdu"])
        tdf_data = client.encrypt_string(origin)
        decrypted_plain_text = client.decrypt_string(tdf_data)
        return decrypted_plain_text

    @staticmethod
    def check_data_is_valid():
        origin = "Hello world!"
        if DataApiTestRunner.encrypt_decrypt(origin) == origin:
            return True
        else:
            raise AssertionError("Decrypted data doesnt match with origin")


class FileApiTestRunner(Assert):
    def run(self):
        self.logger.info(f"******************* Testing File Api encrypt-decrypt ******")

        self.print_result(
            self.assert_pass(FileApiTestRunner.encrypt_decrypt),
            "Encryption and decryption should successfully passed",
        )
        self.print_result(
            self.assert_pass(FileApiTestRunner.encrypt_decrypt),
            "Decrypted data should match original",
        )

    @staticmethod
    def encrypt_decrypt():
        client = TDF3Client(
            eas_url=os.environ["ENTITY_OBJECT_HOST"], user="Charlie_1234"
        )
        client.enable_console_logging(LogLevel.Trace)
        client.with_data_attributes(["https://eas.local/attr/language/value/urdu"])
        client.encrypt_file("resources/sample.txt", "resources/sample.txt.tdf")
        client.decrypt_file("resources/sample.txt.tdf", "resources/sample_out.txt")

    @staticmethod
    def check_data_is_valid():
        sample_text_file = open("resources/sample.txt", "r")
        decrypted_text_file = open("resources/sample_out.txt", "r")

        if sample_text_file == decrypted_text_file:
            return True
        else:
            raise AssertionError("Decrypted data doesnt match with origin")


# Constants
ENCRYPT = "encrypt"
DECRYPT = "decrypt"
SAMPLE_SIZE = 10


class StressTestRunner:
    def __init__(self, size, step):
        self.logger = logging.getLogger(LOGGER_NAME)
        self.size = size
        self.step = step
        self.dir_name = "samples"
        if not os.path.exists("graph"):
            os.makedirs("graph")

    def run(self):
        self.logger.info(f"******************* Stress test run ***********************")

        files = self.create_sample_data()
        self.stress_test(ENCRYPT, files)

        encrypted_files = self.get_tdf3_files_and_sort()
        self.stress_test(DECRYPT, encrypted_files)

    def stress_test(self, action_name, files):
        client = TDF3Client(
            eas_url=os.environ["ENTITY_OBJECT_HOST"], user="Charlie_1234"
        )
        client.enable_console_logging(LogLevel.Trace)
        client.with_data_attributes(["https://eas.local/attr/language/value/urdu"])
        method = client.encrypt_file if action_name == ENCRYPT else client.decrypt_file

        x = []
        y = []
        plt.xlabel("File size mb")
        plt.ylabel("Time (sec)")

        for file in files:
            target_file = os.path.splitext(file)[0]
            sample_space = SAMPLE_SIZE
            file_name = os.path.basename(file)
            params = (
                (file, f"{file}.tdf3")
                if action_name == ENCRYPT
                else (file, target_file)
            )

            time_spent = (
                timeit.Timer(lambda: method(*params)).timeit(number=sample_space)
            ) / sample_space
            size = int(re.search(r"\d+", file_name).group(0))
            x.append(size)
            y.append(time_spent)
            self.logger.info(
                f"Time to {action_name} file: {file_name} - {time_spent:.{3}f} sec"
            )

        plt.clf()
        plt.plot(x, y, "go-", linewidth=2, markersize=5)
        plt.savefig(f"graph/{action_name}.png")

    def create_sample_data(self):
        try:
            self.logger.info("Removing previous stress test data")
            shutil.rmtree(self.dir_name, ignore_errors=True, onerror=None)

            self.logger.info("Creating new data")
            os.mkdir(self.dir_name)

            # NOTE: reuse the 1 mb chuck
            random_str = "".join(
                random.choice(string.ascii_letters + string.digits)
                for _ in range(1024 * 1024)
            )

            out_file_list = []
            current_dir = os.getcwd()
            for size in range(self.step, self.size + self.step, self.step):
                file_name = os.path.join(current_dir, self.dir_name, f"{size}mb.dat")

                out_file_list.append(file_name)
                with open(file_name, "w") as f:
                    for _ in range(0, size):
                        f.write(random_str)
        except:
            exc_info = sys.exc_info()
            raise exc_info[0].with_traceback(exc_info[1], exc_info[2])
        else:
            self.logger.info("Sample data created successfully")

        return out_file_list

    def get_tdf3_files_and_sort(self):
        try:
            all_files = []
            for file in os.listdir(self.dir_name):
                if (
                    not file.startswith(".")
                    and os.path.isfile(os.path.join(self.dir_name, file))
                    and file.endswith(".tdf3")
                ):
                    current_dir = os.getcwd()
                    file_name = os.path.join(current_dir, self.dir_name, file)
                    all_files.append(file_name)

            sorted_files = sorted(all_files, key=os.path.getsize)

        except:
            exc_info = sys.exc_info()
            raise exc_info[0].with_traceback(exc_info[1], exc_info[2])
        return sorted_files


LOGGER_NAME = "virtru-tdf"


def setup_logger():
    pass


if __name__ == "__main__":
    main()
