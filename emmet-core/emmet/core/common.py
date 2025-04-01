from datetime import datetime, timezone
from typing import Any

from monty.json import MontyDecoder
from pydantic import BaseModel, ValidationInfo, model_validator

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


class Status(ValueEnum):
    """
    State of a calculation/analysis.
    """

    SUCCESS = "successful"
    FAILED = "failed"


class ContextModel(BaseModel):
    """
    Overrides BaseModel's init to provide additional positional arg.
    Context can be passed to model constructor to handle deserialization
    of input data types that the default validation handler does not
    understand.
    """

    def __init__(
        self, __context: dict[str, Any] | None = None, /, **data: Any
    ) -> None:  # type: ignore
        __tracebackhide__ = True
        self.__pydantic_validator__.validate_python(
            data, self_instance=self, context=__context
        )

    @model_validator(mode="wrap")
    def model_deserialization(cls, values, default_deserializer, info: ValidationInfo):
        format = info.context.get("format") if info.context else "standard"
        if format == "arrow":
            print("would deserialize arrow inputs!")
            return

        return default_deserializer(values, info)
