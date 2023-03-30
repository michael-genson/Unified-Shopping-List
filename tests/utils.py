import random
import string


def random_string(length=10) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length)).strip()


def random_email(length=10) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length)) + "@example.com"


def random_bool() -> bool:
    return bool(random.getrandbits(1))


def random_int(min=-4294967296, max=4294967296) -> int:
    return random.randint(min, max)
