import re
from typing import Union

mpid_regex = re.compile(r"^([A-Za-z]*-)?(\d+)(-[A-Za-z0-9]+)*$")


class MPID(str):
    """
    A Materials Project type ID with a prefix and an integer
    This class enables seemlessly mixing MPIDs and regular integer IDs
    Prefixed IDs are considered less than non-prefixed IDs to enable proper
    mixing with the Materials Project
    """

    def __init__(self, val: Union["MPID", int, str]):

        if isinstance(val, MPID):
            self.parts = val.parts  # type: ignore
            self.string = val.string  # type: ignore

        elif isinstance(val, int):
            self.parts = (None, val)
            self.string = str(val)

        elif isinstance(val, str):
            parts = val.split("-")
            parts[1] = int(parts[1])  # type: ignore
            self.parts = tuple(parts)
            self.string = val

        else:

            raise ValueError(
                "Must provide an MPID, int, or string of the format prefix-number"
            )

    def __eq__(self, other: object):
        if isinstance(other, MPID):
            return self.string == other.string
        elif isinstance(other, (int, str)):
            return self.string == MPID(other).string

    def __str__(self):
        return self.string

    def __repr__(self):
        return f"MPID({self})"

    def __lt__(self, other: Union["MPID", int, str]):

        # Always sort MPIDs before pure integer IDs
        if isinstance(other, int):
            return True
        elif isinstance(other, str):
            other_parts = MPID(other).parts
        else:
            other_parts = other.parts

        return self.parts < other_parts

    def __hash__(self):
        return hash(self.string)

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
            return MPID(v)
        elif isinstance(v, int):
            return MPID(v)

        raise ValueError("Invalid MPID Format")
