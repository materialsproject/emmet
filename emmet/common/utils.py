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
