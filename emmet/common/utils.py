import os.path

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
        return {k: scrub_class_and_module(v) for k, v in doc.items()
                if not k in ['@class', '@module']}
    elif isinstance(doc, list):
        return [scrub_class_and_module(k) for k in doc]
    else:
        return doc
