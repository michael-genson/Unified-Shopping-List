from typing import Callable


def fully_qualified_name(obj: type | Callable) -> str:
    return ".".join([obj.__module__, obj.__qualname__])
