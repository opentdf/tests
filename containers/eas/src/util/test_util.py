import string
import random


def random_string(string_length: int = 8, lcase: bool = False) -> str:
    letters = string.ascii_letters + string.digits
    if lcase:
        letters = string.ascii_lowercase
    return "".join(random.choice(letters) for _ in range(string_length))
