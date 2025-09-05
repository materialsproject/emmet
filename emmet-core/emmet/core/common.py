from datetime import datetime, timezone
from typing import Annotated
from pydantic import PlainSerializer, BeforeValidator

from monty.json import MontyDecoder

from emmet.core.utils import ValueEnum, utcnow


def convert_datetime(cls, v):
    if not v:
        return utcnow()

    if isinstance(v, dict):
        if v.get("$date"):
            dt = datetime.fromisoformat(v["$date"])
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt

    if isinstance(v, str):
        dt = datetime.fromisoformat(v)
        if not dt.tzinfo:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt

    v = MontyDecoder().process_decoded(v)
    if not v.tzinfo:
        v = v.replace(tzinfo=timezone.utc)
    return v


DateTimeType = Annotated[
    datetime,
    PlainSerializer(lambda x: x.isoformat(), return_type=str),
    BeforeValidator(lambda x: convert_datetime(None, x)),
]


class Status(ValueEnum):
    """
    State of a calculation/analysis.
    """

    SUCCESS = "successful"
    FAILED = "failed"
