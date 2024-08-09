import logging
import subprocess

logger = logging.getLogger("xtest")
logging.basicConfig()
logging.getLogger().setLevel(logging.DEBUG)


sdk_paths = {
    "go": "sdk/go/cli.sh",
    "java": "sdk/java/cli.sh",
    "js": "sdk/js/cli/cli.sh",
}

def encrypt(sdk, pt_file, ct_file, mime_type="application/octet-stream", fmt="nano", attr_values=[]):
    c = [
        sdk_paths[sdk],
        "encrypt",
        pt_file,
        ct_file,
        fmt,
        mime_type,
    ]
    if attr_values:
        c += [",".join(attr_values)]
    logger.debug(f"enc [{' '.join(c)}]")
    subprocess.check_call(c)


def decrypt(sdk, ct_file, rt_file, fmt="nano"):
    c = [
        sdk_paths[sdk],
        "decrypt",
        ct_file,
        rt_file,
        fmt,
    ]
    logger.info(f"dec [{' '.join(c)}]")
    subprocess.check_call(c)
