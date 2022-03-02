#!/usr/bin/env python3
import os
import sys
import timeit
import json
from functools import partial
from tdf3sdk import TDF3Client, LogLevel


class ExecTime:
    @staticmethod
    def for_method(test_method, test_runs_amount):
        average_time = (
            timeit.Timer(test_method).timeit(number=test_runs_amount) / test_runs_amount
        )
        return average_time


class PerformanceTests:
    @staticmethod
    def run():
        client = TDF3Client(eas_url=os.environ["EAS_ENDPOINT"], user="entity1")
        # client.enable_console_logging(LogLevel.Trace)
        message = "Houston, we have a problem"

        print("encrypt")
        # TODO on PLAT-1062
        # client.with_data_attributes(["https://eas.local/attr/0/value/0"])
        tdf_data = client.encrypt_string(message)

        print("time encrypt")
        encrypt = partial(client.encrypt_string, message)
        encryption_time = ExecTime.for_method(encrypt, test_runs_amount=50)

        print("time decrypt")
        decrypt = partial(client.decrypt_string, tdf_data)
        decryption_time = ExecTime.for_method(decrypt, test_runs_amount=50)

        return encryption_time, decryption_time


if len(sys.argv) < 2:
    filePath = "./performance-run-result.json"
else:
    filePath = sys.argv[1]

print("====== Running Performance Tests =======")

(encrypt_time, decrypt_time) = PerformanceTests.run()

result = {"encrypt_time": encrypt_time, "decrypt_time": decrypt_time}

print("========= Write result file ============")
print(result)
with open(filePath, "w") as outfile:
    json.dump(result, outfile)
