from emmet.core.utils import ValueEnum
from datetime import datetime
from monty.json import MontyDecoder


def convert_datetime(cls, v):
    if isinstance(v, dict):
        if v.get("$date"):
            return datetime.fromisoformat(v["$date"])

    return MontyDecoder().process_decoded(v)


class Status(ValueEnum):
    """
    State of a calculation/analysis.
    """

    SUCCESS = "successful"
    FAILED = "failed"
