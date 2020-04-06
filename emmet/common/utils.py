import itertools
import os.path

import bson
import numpy as np
import datetime
from monty.json import MSONable

from monty.serialization import loadfn


def load_settings(settings, default_settings):
    settings = settings if settings else default_settings
    if os.path.exists(settings):
        return loadfn(settings)
    elif isinstance(settings, (dict, list)):
        return settings
    else:
        raise Exception("No settings provided")


def scrub_class_and_module(doc):
    """
    This utility method scrubs a document of it's class and
    module entries.  Note that this works on the doc **in place**.

    Args:
        doc (dict): a nested dictionary to be scrubbed

    Returns:
        A nested dictionary with the module and class attributes
        removed from all subdocuments
    """
    if isinstance(doc, dict):
        return {
            k: scrub_class_and_module(v)
            for k, v in doc.items()
            if k not in ["@class", "@module"]
        }
    elif isinstance(doc, list):
        return [scrub_class_and_module(k) for k in doc]
    else:
        return doc


def get_chemsys_space(chemsys):
    elements = chemsys.split("-")
    combos = itertools.chain.from_iterable(
        itertools.combinations(elements, i) for i in range(1, len(elements) + 1)
    )
    return list("-".join(sorted(combo)) for combo in combos)


def jsanitize(obj, strict=False, allow_bson=False):
    """
    This method cleans an input json-like object, either a list or a dict or
    some sequence, nested or otherwise, by converting all non-string
    dictionary keys (such as int and float) to strings, and also recursively
    encodes all objects using Monty's as_dict() protocol.
    Args:
        obj: input json-like object.
        strict (bool): This parameters sets the behavior when jsanitize
            encounters an object it does not understand. If strict is True,
            jsanitize will try to get the as_dict() attribute of the object. If
            no such attribute is found, an attribute error will be thrown. If
            strict is False, jsanitize will simply call str(object) to convert
            the object to a string representation.
        allow_bson (bool): This parameters sets the behavior when jsanitize
            encounters an bson supported type such as objectid and datetime. If
            True, such bson types will be ignored, allowing for proper
            insertion into MongoDb databases.
    Returns:
        Sanitized dict that can be json serialized.
    """
    if allow_bson and (
        isinstance(obj, (datetime.datetime, bytes))
        or (bson is not None and isinstance(obj, bson.objectid.ObjectId))
    ):
        return obj
    if isinstance(obj, (list, tuple)):
        return [jsanitize(i, strict=strict, allow_bson=allow_bson) for i in obj]
    if np is not None and isinstance(obj, np.ndarray):
        return [
            jsanitize(i, strict=strict, allow_bson=allow_bson) for i in obj.tolist()
        ]
    if isinstance(obj, dict):
        return {
            k.__str__(): jsanitize(v, strict=strict, allow_bson=allow_bson)
            for k, v in obj.items()
        }
    if isinstance(obj, MSONable):
        return {
            k.__str__(): jsanitize(v, strict=strict, allow_bson=allow_bson)
            for k, v in obj.as_dict().items()
        }

    if isinstance(obj, (int, float)):
        return obj
    if obj is None:
        return None

    if isinstance(obj, MSONable):
        return {
            k.__str__(): jsanitize(v, strict=strict, allow_bson=allow_bson)
            for k, v in obj.as_dict().items()
        }

    if not strict:
        return obj.__str__()

    if isinstance(obj, str):
        return obj.__str__()

    return jsanitize(obj.as_dict(), strict=strict, allow_bson=allow_bson)
