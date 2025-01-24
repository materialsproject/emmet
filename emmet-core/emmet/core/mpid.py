# %%
from __future__ import annotations
from math import log, floor
import re
from string import ascii_lowercase
from typing import Union, Any, Callable, TYPE_CHECKING

from pydantic_core import CoreSchema, core_schema

from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue

if TYPE_CHECKING:
    from typing_extensions import Self

# matches "mp-1234" or "1234" followed by and optional "-(Alphanumeric)"
mpid_regex = re.compile(r"^([A-Za-z]*-)?(\d+)(-[A-Za-z0-9]+)*$")
mpculeid_regex = re.compile(
    r"^([A-Za-z]+-)?([A-Fa-f0-9]+)-([A-Za-z0-9]+)-(m?[0-9]+)-([0-9]+)$"
)
# matches capital letters and numbers of length 26 (ULID)
# followed by and optional "-(Alphanumeric)"
check_ulid = re.compile(r"^[A-Z0-9]{26}(-[A-Za-z0-9]+)*$")


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
            if mpid_regex.fullmatch(val):
                parts = val.split("-")
                parts[1] = int(parts[1])  # type: ignore
                self.parts = tuple(parts)
            elif check_ulid.fullmatch(val):
                ulid = val.split("-")[0]
                self.parts = (ulid, 0)
            else:
                raise ValueError(
                    "MPID string representation must follow the format prefix-number or start with a valid ULID."
                )
            self.string = val

        else:
            raise ValueError(
                "Must provide an MPID, int, or string of the format prefix-number or start with a valid ULID."
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
    def __get_pydantic_core_schema__(
        cls, source: type[Any], handler: Callable[[Any], core_schema.CoreSchema]
    ) -> core_schema.CoreSchema:
        return core_schema.with_info_plain_validator_function(cls.validate)

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return dict(
            pattern=r"^([A-Za-z]*-)?(\d+)(-[A-Za-z0-9]+)*$",
            examples=["mp-3534", "3453", "mp-834-Ag"],
            type="string",
        )

    @classmethod
    def validate(cls, __input_value: Any, _: core_schema.ValidationInfo):
        if isinstance(__input_value, MPID):
            return __input_value
        elif isinstance(__input_value, str) and mpid_regex.fullmatch(__input_value):
            return MPID(__input_value)
        elif isinstance(__input_value, str) and check_ulid.fullmatch(__input_value):
            return MPID(__input_value)
        elif isinstance(__input_value, int):
            return MPID(__input_value)

        raise ValueError("Invalid MPID Format")


# %%


class MPculeID(str):
    """
    A Materials Project Molecule ID with a prefix, hash, and two integer values
        representing the charge and spin of the molecule
    Unlike the MPID, you cannot compare raw hashes or raw integers to MPculeIDs

    Args:
        val: Either 1) an MPculeID
                    2) a prefixed string of format "prefix-hash-formula-charge-spin"
                    3) a non-prefixed string of format "hash-formula-charge-spin"

            Numbers stored as strings are coerced to ints
    """

    def __init__(self, val: Union["MPculeID", str]):
        if isinstance(val, MPculeID):
            self.parts = val.parts  # type: ignore
            self.string = val.string  # type: ignore

        elif isinstance(val, str):
            parts = val.split("-")
            if len(parts) == 4:
                parts[1] = int(parts[2].replace("m", "-"))  # type: ignore
                parts[2] = int(parts[3])  # type: ignore
            elif len(parts) == 5:
                parts[3] = int(parts[3].replace("m", "-"))  # type: ignore
                parts[4] = int(parts[4])  # type: ignore
            else:
                raise ValueError(
                    "MPculeID string representation must follow the "
                    "format prefix-hash-formula-charge-spin or hash-formula-charge-spin."
                )

            self.parts = tuple(parts)
            self.string = val

        else:
            raise ValueError(
                "Must provide an MPculeID, or string of the format prefix-hash-formula-charge-spin "
                "or hash-formula-charge-spin"
            )

    def __eq__(self, other: object):
        if isinstance(other, MPculeID):
            return self.string == other.string
        elif isinstance(other, str):
            return self.string == MPculeID(other).string

    def __str__(self):
        return self.string

    def __repr__(self):
        return f"MPculeID({self})"

    def __lt__(self, other: Union["MPculeID", str]):
        other_parts = MPculeID(other).parts

        return "-".join([str(x) for x in self.parts[-4:]]) < "-".join(
            [str(x) for x in other_parts[-4:]]
        )

    def __gt__(self, other: Union["MPculeID", str]):
        return not self.__lt__(other)

    def __hash__(self):
        return hash(self.string)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: type[Any], handler: Callable[[Any], core_schema.CoreSchema]
    ) -> core_schema.CoreSchema:
        return core_schema.with_info_plain_validator_function(cls.validate)

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        return dict(
            pattern=r"^^([A-Za-z]+-)?([A-Fa-f0-9]+)-([A-Za-z0-9]+)-(m?[0-9]+)-([0-9]+)$",
            examples=[
                "1a525231bdac3f13e2fac0962fe8d053-Mg1-0-1",
                "22b40b99719ac570fc7e6225e855ec6e-F5Li1P1-m1-2",
                "mpcule-b9ba54febc77d2a9177accf4605767db-C1H41-2",
            ],
            type="string",
        )

    @classmethod
    def validate(cls, __input_value: Any, _: core_schema.ValidationInfo):
        if isinstance(__input_value, MPculeID):
            return __input_value
        elif isinstance(__input_value, str) and mpculeid_regex.fullmatch(__input_value):
            return MPculeID(__input_value)

        raise ValueError("Invalid MPculeID Format")


# %%


class AlphaID(str):
    """Identifier based on representing an integer as an alphabetical string.

    Args:
        _alphabet (str) : The alphabet to use, defaults to lowercase Roman.
        _default_separator (str) : The separator between prefix and identifier
            string, if a prefix is used.
    """

    _alphabet: str = ascii_lowercase

    def __new__(
        cls,
        identifier: str | int,
        padlen: int = 0,
        prefix: str | None = None,
        separator: str = "-",
    ) -> Self:
        """Define a new instance of AlphaID.

        Args:
            identifier (str or int) : the identifier, either a string with characters belonging
                to AlphaID._alphabet, or an integer to represent as a string.
            padlen (int, default = 0) : the amount of characters to pad to if a character
                string is too short. For example,
        """

        if isinstance(identifier, int):
            identifier = cls._integer_to_alpha_rep(identifier)
        padded = max(0, padlen - len(identifier)) * cls._alphabet[0]
        prefix = prefix or ""
        if len(prefix) == 0:
            separator = ""

        new_cls = str.__new__(cls, prefix + separator + padded + identifier)
        new_cls._identifier = identifier
        new_cls._padlen = padlen
        new_cls._prefix = prefix
        new_cls._separator = separator
        return new_cls

    @classmethod
    def _string_to_base_10_value(cls, string: str) -> int:
        value = 0
        rev_codex = {letter: idx for idx, letter in enumerate(cls._alphabet)}
        base = len(cls._alphabet)
        for ipow, char in enumerate(string[::-1]):
            value += rev_codex[char] * base**ipow
        return value

    @classmethod
    def _integer_to_alpha_rep(cls, integer: int) -> str:
        if integer == 0:
            return cls._alphabet[0]

        base = len(cls._alphabet)
        max_pow = floor(log(integer) / log(base))
        string: str = ""
        rem = integer
        for pow in range(max_pow, -1, -1):
            if rem == 0:
                string += cls._alphabet[0]
                continue
            mult = base**pow
            for coeff in range(base - 1, -1, -1):
                if coeff * mult <= rem:
                    string += cls._alphabet[coeff]
                    rem -= coeff * mult
                    break
        return string

    def __int__(self) -> int:
        return self._string_to_base_10_value(self._identifier)

    def __repr__(self):
        return "AlphaID(" + self + ")"

    def __add__(self, other: str | int) -> "AlphaID":
        """Define addition of AlphaID.

        Returns an AlphaID with the equal or greater length than the current
        instance and the same prefix.

        Args:
            other (str or int) : the value to add to the current identifier.
                If a string, its integer value is first computed.
                The integer values are then added, and a new instance
                of AlphaID is returned.
        Returns:
            AlphaID representing the sum of the current and other values.
        """
        if isinstance(other, AlphaID):
            other = self._string_to_base_10_value(other._identifier)
        elif isinstance(other, str):
            other = self._string_to_base_10_value(other)

        return AlphaID(
            int(self) + other,
            padlen=self._padlen,
            prefix=self._prefix,
            separator=self._separator,
        )

    def __sub__(self, other: str | int) -> "AlphaID":
        if isinstance(other, AlphaID):
            other = self._string_to_base_10_value(other._identifier)
        elif isinstance(other, str):
            other = self._string_to_base_10_value(other)
        return self.__add__(-other)
