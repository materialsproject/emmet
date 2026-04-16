"""Define generic monty serdes."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any


class MSONType(BaseModel):

    module: str = Field(validation_alias="@module")
    klass: str = Field(validation_alias="@class")
    version: str | None = Field(None, validation_alias="@version")
    callable: str | None = Field(None, validation_alias="@callable")
    bound: str | None = Field(None, validation_alias="@bound")

    def as_dict(self) -> dict[str, str | None]:
        """Return MSON-style dict."""
        dct = {
            field.validation_alias: getattr(self, k)
            for k, field in self.__class__.model_fields.items()
        }
        return {k: v for k, v in dct.items() if v is not None}

    @classmethod
    def from_dict(cls, dct) -> Any:
        """Mimic monty decoding.

        Doesn't need to be a classmethod, but is included here
        for duck-typing.
        """
        from monty.json import MontyDecoder

        return MontyDecoder().process_decoded(dct)
