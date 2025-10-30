import os

import tdfs

small_plaintext_file = "small-golden.txt"
large_plaintext_file = "large-golden.txt"

def create_test_file(size_in_bytes, name):
    # Create a bytes object filled with zeros
    data = bytes([0] * size_in_bytes)
    # Write the data to a text file
    with open(name, "wb") as file:
        file.write(data)
    

def create_golden_tdfs():
    create_test_file(5 * 2**10, small_plaintext_file)
    create_test_file(10 * 2**20, large_plaintext_file)

    xtest_dir = os.path.dirname(os.path.realpath(__file__))

    create_golden = os.getenv("CREATE_GOLDEN", "").split(",")
    for sdk in create_golden:
        if sdk in tdfs.sdk_paths:
            golden_file_name = ""
            if sdk == "java":
                java_ref = os.getenv("JAVA_REF", "")
                golden_file_name = f"{sdk}-{java_ref}.tdf"
            elif sdk == "go":
                go_ref = os.getenv("PLATFORM_REF", "")
                golden_file_name = f"{sdk}-{go_ref}.tdf"
            elif sdk == "js":
                js_version = os.getenv("JS_VERSION", "")
                if not js_version:
                    js_version = os.getenv("JS_REF", "")
                golden_file_name = f"{sdk}-{js_version}.tdf"
            else:
                ## This should never happen
                raise RuntimeError(f"Unknown SDK: {sdk}")
            tdfs.encrypt(
                sdk, 
                small_plaintext_file, 
                os.path.join(xtest_dir, "golden", f"small-{golden_file_name}"),
                mime_type="text/plain",
                fmt="ztdf")
            tdfs.encrypt(
                sdk, 
                large_plaintext_file, 
                os.path.join(xtest_dir, "golden", f"large-{golden_file_name}"),
                mime_type="text/plain",
                fmt="ztdf")
            
def main():
    create_golden_tdfs()

