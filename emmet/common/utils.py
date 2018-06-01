import os

from monty.serialization import loadfn


def load_settings(settings, default_settings):
    if os.path.is_path(settings):
        return loadfn(settings)
    elif isinstance(settings, (dict, list)):
        return settings
    return loadfn(default_settings)

