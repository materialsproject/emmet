import re
from dataclasses import dataclass
from typing import Union

NOTHING = object()

mpid_regex = re.compile(r"^([A-Za-z]*-)?(\d+)(-[A-Za-z0-9]+)*$")


class MPID:
    """
    A Materials Project type ID with a prefix and an integer
    This class enables seemlessly mixing MPIDs and regular integer IDs
    Prefixed IDs are considered less than non-prefixed IDs to enable proper
    mixing with the Materials Project
    """

    def __init__(self, val: Union["MPID", int, str]):

        if isinstance(val, MPID):
            self.parts = val.parts

        elif isinstance(val, int):
            self.parts = (NOTHING, val)

        elif isinstance(val, str):
            parts = val.split("-")
            parts[1] = int(parts[1])
            self.parts = tuple(parts)

    def __eq__(self, other: Union["MPID", int, str]):
        return self.parts == other.parts

    def __str__(self):
        return "-".join(self.parts)

    def __lt__(self, other: Union["MPID", int, str]):

        # Always sort MPIDs before pure integer IDs
        if isinstance(other, int):
            return True
        elif isinstance(other, str):
            other_parts = other.split("-")
            other_parts[1] = int(other_parts[1])
        else:
            other_parts = other.parts

        return self.parts < other_parts

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(
            pattern=r"^([A-Za-z]*-)?(\d+)(-[A-Za-z0-9]+)*$",
            examples=["mp-3534", "3453", "mp-834-Ag"],
        )

    @classmethod
    def validate(cls, v):

        if isinstance(v, MPID):
            return v
        elif isinstance(v, str) and mpid_regex.fullmatch(v):
            return v

        raise ValueError("Invalid MPID Format")
