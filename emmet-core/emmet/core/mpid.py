"""Define identifier schemas used in MP."""
from __future__ import annotations

from math import log, floor
import re
from string import ascii_lowercase, digits
from typing import TYPE_CHECKING

from pydantic_core import CoreSchema, core_schema

from pydantic import GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any
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

    def __init__(self, val: MPID | int | str):
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

    def __lt__(self, other: MPID | int | str):
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

    def __gt__(self, other: MPID | int | str):
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

    def __init__(self, val: MPculeID | str):
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

    def __lt__(self, other: MPculeID | str):
        other_parts = MPculeID(other).parts

        return "-".join([str(x) for x in self.parts[-4:]]) < "-".join(
            [str(x) for x in other_parts[-4:]]
        )

    def __gt__(self, other: MPculeID | str):
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


class AlphaID(str):
    """Identifier based on representing an integer as an alphabetical string.

    Args:
        _alphabet (str) : The alphabet to use, defaults to lowercase Roman.
        _identifier (str) : The alphabetical string identifier.
        _padlen (int) : The minimum length of an identifier to pad left with zeroes.
        _prefix (str) : The ID prefix, ex. "mp"
        _separator (str) : The separator between `_prefix` and `_identifier`, ex: "-"
    """

    _identifier: str
    _padlen: int
    _prefix: str
    _separator: str
    _alphabet: str = ascii_lowercase
    _value: int | None = None

    def __new__(
        cls,
        identifier: str | int | MPID,
        padlen: int = 0,
        prefix: str | None = None,
        separator: str = "-",
    ) -> Self:
        """Define a new instance of AlphaID.

        Args:
            identifier (str, int, or MPID) : the identifier, either a string with characters belonging
                to AlphaID._alphabet, an integer to represent as a string, or an MPID.
            padlen (int, default = 0) : the amount of characters to pad to if a character
                string is too short. For example, the integer 149 has alpha representation "ft",
                and thus `AlphaID(149, padlen = 6)` would present as "aaaaft".
                Both "ft" and "aaaaft" have the same integer value.
            prefix (str or None, default = None) : if a str, the prefix to use.
                For example, `AlphaID(149, padlen = 6, prefix="mp")` would present as "mp-aaaaft".
            separator (str, default = "-") : the separator to use between the prefix and the
                string representation of the integer, if the prefix is non-empty.
                For example, `AlphaID(149, padlen = 6, prefix="mp", separator = ":")` would
                present as "mp:aaaaft".
        """

        if isinstance(identifier, str):
            if (
                len(
                    non_alpha_char := set(identifier).difference(cls._alphabet + digits)
                )
                == 1
            ):
                separator = list(non_alpha_char)[0]
                prefix, identifier = identifier.split(separator)
            elif len(non_alpha_char) > 1:
                raise ValueError(
                    f"Too many non-alpha-numeric characters: {', '.join(non_alpha_char)}"
                )

        elif isinstance(identifier, MPID):
            split_mpid = identifier.string.split("-")
            if len(split_mpid) == 1:
                identifier = split_mpid[0]
            else:
                prefix, identifier = split_mpid
                separator = "-"

        if isinstance(identifier, str):
            identifier = int(identifier)
        if isinstance(identifier, int):
            identifier = cls._integer_to_alpha_rep(identifier)

        prefix = prefix or ""
        if len(prefix) == 0:
            separator = ""

        padded = max(0, padlen - len(identifier)) * cls._alphabet[0]
        new_cls = str.__new__(cls, prefix + separator + padded + identifier)
        new_cls._identifier = identifier
        new_cls._padlen = padlen
        new_cls._prefix = prefix
        new_cls._separator = separator
        return new_cls

    @classmethod
    def _string_to_base_10_value(cls, string: str) -> int:
        """Obtain the integer value of an alphabetical string."""
        value = 0
        rev_codex = {letter: idx for idx, letter in enumerate(cls._alphabet)}
        base = len(cls._alphabet)
        for ipow, char in enumerate(string[::-1]):
            value += rev_codex[char] * base**ipow
        return value

    @classmethod
    def _integer_to_alpha_rep(cls, integer: int) -> str:
        """Obtain the string representation of an integer."""
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
        """Get and cache the current AlphaID's integer value."""
        if self._value is None:
            self._value = self._string_to_base_10_value(self._identifier)
        return self._value

    def __repr__(self):
        """Set AlphaID display name to distinguish from base string class."""
        return "AlphaID(" + self + ")"

    def __eq__(self, other: Any) -> bool:
        """Define equality of AlphaID.

        If other is an int, returns True if the integer value of the
        current instance equals the other.

        If other is a base str, returns True if the string reprentations
        are equal.

        If other is an AlphaID, returns True only if the prefix, separator,
        and value of the two are equal.
        """
        if isinstance(other, MPID):
            test = AlphaID(other)
        else:
            test = other

        if isinstance(test, int):
            return int(self) == test
        elif isinstance(test, AlphaID):
            return (
                test._prefix == self._prefix
                and test._separator == self._separator
                and int(self) == int(test)
            )
        elif isinstance(test, str):
            return self == str(test)
        raise NotImplementedError(f"Cannot compare AlphaID with {type(test)}")

    def __ne__(self, other: Any) -> bool:
        """Define inverse equality for AlphaID."""
        return not self.__eq__(other)

    def __add__(self, other: Any) -> "AlphaID":
        """Define addition of AlphaID.

        Returns an AlphaID with the same `padlen` as the current instance, not `other`.
        Thus the order of addition can change the presentation of AlphaID, but not
        its value.

        If other is also an AlphaID, but its `prefix` and `separator` do not match,
        will not add the two. Only checks the separator if prefixes are both non-null.

        Args:
            other (str or int) : the value to add to the current identifier.
                If a string, its integer value is first computed.
                The integer values are then added, and a new instance
                of AlphaID is returned.
        Returns:
            AlphaID representing the sum of the current and other values.
        """

        if isinstance(other, MPID):
            test = AlphaID(other)
        else:
            test = other

        if isinstance(test, AlphaID):
            exc_str = ""
            if test._prefix != self._prefix:
                exc_str += f"Prefixes do not match: left = {self._prefix or None}, right {test._prefix or None}. "

            if test._prefix and self._prefix and test._separator != self._separator:
                exc_str += f"Separators do not match: left = {self._separator}, right {test._separator}."

            if exc_str:
                raise TypeError(exc_str)

            diff = self._string_to_base_10_value(test._identifier)
        elif isinstance(test, str):
            diff = self._string_to_base_10_value(test)
        elif not isinstance(test, int):
            raise NotImplementedError(f"Cannot add AlphaID to type {type(test)}")

        return AlphaID(
            int(self) + diff,
            padlen=self._padlen,
            prefix=self._prefix,
            separator=self._separator,
        )

    def __sub__(self, other: Any) -> "AlphaID":
        """Define subtraction of AlphaID.

        See the docstring for `__add__`. The resultant `padlen` is taken
        from the current instance, not `other`.

        Will not subtract two AlphaIDs if `prefix` and `separator` do not match.
        """
        if isinstance(other, AlphaID):
            test = self._string_to_base_10_value(other._identifier)
        elif isinstance(other, MPID):
            test = self._string_to_base_10_value(AlphaID(other)._identifier)
        elif isinstance(other, str):
            test = self._string_to_base_10_value(other)
        else:
            test = other
        return self.__add__(-test)

    def __lt__(self, other: Any) -> bool:
        """Define AlphaID less than.

        Returns False between two AlphaIDs if `prefix` and `separator` do not match.
        """
        if isinstance(other, MPID):
            test = AlphaID(other)
        else:
            test = other

        if isinstance(test, int):
            return int(self) < test
        elif isinstance(test, AlphaID):
            if test._prefix == self._prefix and test._separator == self._separator:
                return int(self) < int(test)
            return False
        elif isinstance(test, str):
            return int(self) < self._string_to_base_10_value(test)
        raise NotImplementedError(f"Cannot compare AlphaID with {type(test)}")

    def __gt__(self, other: Any) -> bool:
        """Define AlphaID greater than.

        Returns False between two AlphaIDs if `prefix` and `separator` do not match.
        """
        if isinstance(other, MPID):
            test = AlphaID(other)
        else:
            test = other

        if isinstance(test, AlphaID) and (
            self._prefix != test._prefix
            or (self._prefix == test._prefix and self._separator != test._separator)
        ):
            return False

        return not self.__lt__(test)
