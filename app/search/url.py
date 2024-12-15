from typing import Any, Generator, Optional
from itertools import chain, starmap
from urllib.parse import urlencode


def flatten_dict(dictionary: dict[Any, Any]) -> dict[Any, Any]:
    """Flatten a nested dictionary structure"""

    def unpack(
        parent_key: Any, parent_value: Any
    ) -> Generator[tuple[Any, Any], None, None]:
        """Unpack one level of nesting in a dictionary"""
        try:
            items = parent_value.items()
        except AttributeError:
            # parent_value was not a dict, no need to flatten
            yield (parent_key, parent_value)
        else:
            for key, value in items:
                if type(value) is list:
                    for k, v in enumerate(value):
                        yield (parent_key + "[" + key + "]" + "[" + str(k) + "]", v)
                else:
                    yield (parent_key + "[" + key + "]", value)

    while True:
        # Keep unpacking the dictionary until all value's are not dictionary's
        dictionary = dict(chain.from_iterable(starmap(unpack, dictionary.items())))
        if not any(isinstance(value, dict) for value in dictionary.values()):
            break
    return dictionary

def encode_params(params: dict):
    return urlencode(flatten_dict(params))
