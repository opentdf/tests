import os

curr_dir = os.path.dirname(__file__)
path = os.path.join(curr_dir, "VERSION")
with open(path, "r") as ver:
    __version__ = ver.read().rstrip()
