from typing import Callable, Union


def fully_qualified_name(obj: Union[type, Callable]) -> str:
    return ".".join([obj.__module__, obj.__qualname__])
