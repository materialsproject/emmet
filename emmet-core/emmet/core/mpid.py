import re
from typing import Union

mpid_regex = re.compile(r"^([A-Za-z]*-)?(\d+)(-[A-Za-z0-9]+)*$")


class MPID(str):
    """
    A Materials Project type ID with a prefix and an integer
    This class enables seemlessly mixing MPIDs and regular integer IDs
    Prefixed IDs are considered less than non-prefixed IDs to enable proper
    mixing with the Materials Project

    Args:
        val: Either 1) a prefixed string e.g. "mp-1234"
                    2) an integer e.g. 1234
                    3) a number stored as a string e.g. '1234'
                    4) an MPID

            Numbers stored as strings are coerced to ints
    """

    def __init__(self, val: Union["MPID", int, str]):

        if isinstance(val, MPID):
            self.parts = val.parts  # type: ignore
            self.string = val.string  # type: ignore

        elif isinstance(val, int) or (isinstance(val, str) and val.isnumeric()):
            self.parts = ("", int(val))
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

        other_parts = MPID(other).parts

        if self.parts[0] != "" and other_parts[0] != "":
            # both have prefixes; normal comparison
            return self.parts < other_parts
        elif self.parts[0] != "":
            # other is a pure int, self is prefixed
            # Always sort MPIDs before pure integer IDs
            return True
        elif other_parts[0] != "":
            # self is pure int, other is prefixed
            return False
        else:
            # both are pure ints; normal comparison
            return self.parts[1] < other_parts[1]

    def __gt__(self, other: Union["MPID", int, str]):
        return not self.__lt__(other)

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
