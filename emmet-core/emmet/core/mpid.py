"""Define identifier schemas used in MP."""

from __future__ import annotations

from math import log, floor
import re
from pathlib import Path
from string import ascii_lowercase, digits
from typing import TYPE_CHECKING

from pydantic_core import CoreSchema, core_schema

# For dev_scripts compatibility, safe import this list
if (Path(__file__).parent / "_forbidden_alpha_id.py").exists():
    from emmet.core._forbidden_alpha_id import FORBIDDEN_ALPHA_ID_VALUES
else:
    FORBIDDEN_ALPHA_ID_VALUES = set()

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any
    from typing_extensions import Self

    from pydantic import GetJsonSchemaHandler
    from pydantic.json_schema import JsonSchemaValue

# matches "mp-1234" or "1234" followed by and optional "-(Alphanumeric)"
MPID_REGEX_PATTERN = r"^([A-Za-z]+-)?(\d+)(-[A-Za-z0-9]+)*$"
mpid_regex = re.compile(MPID_REGEX_PATTERN)

MPCULE_REGEX_PATTERN = (
    r"^([A-Za-z]+-)?([A-Fa-f0-9]+)-([A-Za-z0-9]+)-(m?[0-9]+)-([0-9]+)$"
)
mpculeid_regex = re.compile(MPCULE_REGEX_PATTERN)

# matches capital letters and numbers of length 26 (ULID)
# followed by and optional "-(Alphanumeric)"
check_ulid = re.compile(r"^[A-Z0-9]{26}(-[A-Za-z0-9]+)*$")

VALID_ALPHA_SEPARATORS: set[str] = {
    "-",
    ":",
    "_",
}


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

    def __init__(self, val: MPID | int | str) -> None:
        if isinstance(val, MPID):
            self.parts = val.parts  # type: ignore
            self.string = val.string  # type: ignore

        elif isinstance(val, int) or (isinstance(val, str) and val.isnumeric()):
            if int(val) < 0:
                raise ValueError("MPID cannot represent a negative integer.")
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

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, MPID):
            return self.string == other.string
        elif isinstance(other, AlphaID):
            return other == self
        elif isinstance(other, (int, str)):
            return self.string == MPID(other).string
        return NotImplemented

    def __str__(self) -> str:
        return self.string

    def __repr__(self) -> str:
        return f"MPID({self})"

    def __lt__(self, other: MPID | int | str) -> bool:
        other_parts = MPID(other).parts

        if self.parts[0] and other_parts[0]:
            # both have prefixes; normal comparison
            return self.parts < other_parts
        elif self.parts[0]:
            # other is a pure int, self is prefixed
            # Always sort MPIDs before pure integer IDs
            return True
        elif other_parts[0]:
            # self is pure int, other is prefixed
            return False

        # both are pure ints; normal comparison
        return self.parts[1] < other_parts[1]

    def __gt__(self, other: MPID | int | str) -> bool:
        """Define greater than for MPID.

        Note that `__gt__` is not the same as `not __lt__`.
        If two values are equal, `__lt__` will return False.
        Defining
        ```__gt__ := not __lt__```
        will then incorrectly return True for equal values.
        """
        other_parts = MPID(other).parts

        if self.parts[0] and other_parts[0]:
            # both have prefixes; normal comparison
            return self.parts > other_parts
        elif not self.parts[0] and not other_parts[0]:
            # both are pure ints; normal comparison
            return self.parts[1] > other_parts[1]
        return not self.__lt__(other)

    def __hash__(self) -> int:
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
            pattern=MPID_REGEX_PATTERN,
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

    def __eq__(self, other: object) -> bool:
        if isinstance(other, MPculeID):
            return self.string == other.string
        elif isinstance(other, str):
            return self.string == MPculeID(other).string
        return NotImplemented

    def __str__(self) -> str:
        return self.string

    def __repr__(self) -> str:
        return f"MPculeID({self})"

    def __lt__(self, other: MPculeID | str) -> bool:
        other_parts = MPculeID(other).parts

        return "-".join([str(x) for x in self.parts[-4:]]) < "-".join(
            [str(x) for x in other_parts[-4:]]
        )

    def __gt__(self, other: MPculeID | str) -> bool:
        return not self.__lt__(other)

    def __hash__(self) -> int:
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
        _cut_point (int or None) : For legacy purposes, all MPIDs minted before the
            transition to AlphaID will use the legacy format as `mp-<int>` when
            calling `AlphaID(...).string`.

            Thus `_cut_point`, if not `None`, defines the maximum MPID at which
            the integer in `AlphaID(...).string` is preferred.


    Notes:
        There is possibility for "obscene" strings to be used in AlphaID.
        For a comprehensive list of integer values of these IDs, you can
        import them:
        ```
        from pathlib import Path
        from importlib_resources import files as import_resource_file
        if (Path(import_resource_file("emmet.core")) / "_forbidden_alpha_id.py").exists():
            from emmet.core._forbidden_alpha_id import FORBIDDEN_ALPHA_ID_VALUES
        else:
            FORBIDDEN_ALPHA_ID_VALUES = set()
        ```

        Or run `generate_identifier_exclude_list.py` in `emmet-core/dev_scripts`
    """

    _identifier: str
    _padlen: int
    _prefix: str
    _separator: str
    _alphabet: str = ascii_lowercase
    _value: int | None = None
    _cut_point: int | None = 3347529

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
            if any(char.isupper() for char in identifier):
                raise ValueError(
                    "To avoid amibiguities, AlphaID does not permit uppercase letters."
                )
            non_alpha_char = set(identifier).difference(cls._alphabet + digits)
            valid_seps = non_alpha_char.intersection(VALID_ALPHA_SEPARATORS) > set()
            if len(non_alpha_char) == 1 and valid_seps:
                separator = list(non_alpha_char)[0]
                prefix, identifier = identifier.split(separator)

                if not prefix or not identifier:
                    raise ValueError(
                        "Missing prefix and/or identifer."
                        "To specify an AlphaID without a prefix, provide only the identifier."
                    )

            elif len(non_alpha_char) > 1 or (
                len(non_alpha_char) == 1 and not valid_seps
            ):
                raise ValueError(
                    f"Too many non-alpha-numeric characters: {', '.join(non_alpha_char)}"
                )

        elif isinstance(identifier, MPID):
            prefix, identifier = identifier.parts
            separator = "-"

        if isinstance(identifier, str) and set(identifier).intersection(digits):
            identifier = int(identifier)
        if isinstance(identifier, int):
            if identifier < 0:
                raise ValueError("AlphaID cannot represent a negative integer.")
            identifier = cls._integer_to_alpha_rep(identifier)

        prefix = prefix or ""
        if not prefix:
            separator = ""

        padded = max(0, padlen - len(identifier)) * cls._alphabet[0]
        if separator and separator not in VALID_ALPHA_SEPARATORS:
            raise ValueError(
                f"Invalid separator: {separator}. Use one of: {', '.join(VALID_ALPHA_SEPARATORS)}"
            )
        new_cls = str.__new__(cls, prefix + separator + padded + identifier)
        new_cls._identifier = identifier
        new_cls._padlen = padlen
        new_cls._prefix = prefix
        new_cls._separator = separator
        return new_cls

    @property
    def padded(self) -> str:
        """Return the padded string identifier (without prefixing)."""
        padded = max(0, self._padlen - len(self._identifier)) * self._alphabet[0]
        return f"{padded}{self._identifier}"

    @classmethod
    def _string_to_base_10_value(cls, string_value: str) -> int:
        """Obtain the integer value of an alphabetical string."""
        value = 0
        rev_codex = {letter: idx for idx, letter in enumerate(cls._alphabet)}
        base = len(cls._alphabet)
        for ipow, char in enumerate(string_value[::-1]):
            value += rev_codex[char] * base**ipow
        return value

    @classmethod
    def _integer_to_alpha_rep(cls, integer_val: int) -> str:
        """Obtain the string representation of an integer."""
        if integer_val == 0:
            return cls._alphabet[0]

        base = len(cls._alphabet)
        max_pow = floor(log(integer_val) / log(base))
        string: str = ""
        rem = integer_val
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
            else:
                # Should never reach this point but still good to have this here
                raise ValueError(
                    f"Could not parse integer into string representation: {integer_val}"
                )
        return string

    def __hash__(self) -> int:
        """Ensure hashability."""
        return hash(str(self))

    def __int__(self) -> int:
        """Get and cache the current AlphaID's integer value."""
        if self._value is None:
            self._value = self._string_to_base_10_value(self._identifier)
        return self._value

    def __repr__(self) -> str:
        """Set AlphaID display name to distinguish from base string class."""
        return "AlphaID(" + self + ")"

    def __eq__(self, other: Any) -> bool:
        """Define equality of AlphaID.

        If other is an int, returns True if the integer value of the
        current instance equals the other.

        If other is a base str, returns True if the string representations
        are equal.

        If other is an AlphaID, returns True only if the prefix, separator,
        and value of the two are equal.
        """
        if isinstance(other, MPID) or (
            isinstance(other, str) and other.startswith("mp-")
        ):
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
            return str(self) == test
        raise NotImplementedError(f"Cannot compare AlphaID with {type(test)}")

    def __ne__(self, other: Any) -> bool:
        """Define inverse equality for AlphaID."""
        return not self.__eq__(other)

    @staticmethod
    def _coerce_value(
        alpha_id: AlphaID, other: Any, exception_on_mismatch: bool = True
    ) -> int:
        """Check if another value is comparable to a reference AlphaID.

        Used in defining `__add__`, `__sub__`, `__gt__`, and `__lt_``.

        Args:
            alpha_id : AlphaID
            other : Any other value
            exception_on_mismatch : bool (True = default)
                If True, raises an exception when the prefix and separators
                of two AlphaIDs do not match.

                To allow sorting of AlphaIDs, this is False for `__gt__` and `__lt__`
                but is True for `__add__` and `__sub__`.

        Returns:
            integer reprsenting the other value if possible.
            Raises exceptions if `other` cannot be compared to `alpha_id`.
        """
        test = AlphaID(other) if isinstance(other, MPID) else other

        if isinstance(test, AlphaID):
            if exception_on_mismatch:
                exc_str = ""
                if test._prefix != alpha_id._prefix:
                    exc_str += f"Prefixes do not match\n  left {alpha_id._prefix or None}\n  right {test._prefix or None}"

                if (
                    test._prefix
                    and alpha_id._prefix
                    and test._separator != alpha_id._separator
                ):
                    if exc_str:
                        exc_str += "\n"
                    exc_str += f"Separators do not match:\n  left {alpha_id._separator}\n  right {test._separator}"

                if exc_str:
                    raise TypeError(exc_str)

            diff = int(test)
        elif isinstance(test, str):
            diff = alpha_id._string_to_base_10_value(test)
        elif isinstance(test, int):
            diff = test
        else:
            raise NotImplementedError(f"Cannot compare AlphaID with type {type(test)}")

        return diff

    def __add__(self, other: Any) -> "AlphaID":
        """Define addition of AlphaID.

        Returns an AlphaID with the same `padlen` as the current instance, not `other`.
        Thus the order of addition can change the presentation of AlphaID, but not
        its value.

        If other is also an AlphaID, but its `prefix` and `separator` do not match,
        will not add the two. Only checks the separator if prefixes are both non-null.

        Args:
            other : the value to add to the current identifier.
                If a string, its integer value is first computed.
                The integer values are then added, and a new instance
                of AlphaID is returned.
        Returns:
            AlphaID representing the sum of the current and other values.
        """
        return AlphaID(
            int(self) + self._coerce_value(self, other),
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
        return self.__add__(-self._coerce_value(self, other))

    def __lt__(self, other: Any) -> bool:
        """Define AlphaID less than.

        Returns False between two AlphaIDs if `prefix` and `separator` do not match.
        """
        return int(self) < self._coerce_value(self, other, exception_on_mismatch=False)

    def __gt__(self, other: Any) -> bool:
        """Define AlphaID greater than.

        Returns False between two AlphaIDs if `prefix` and `separator` do not match.
        """
        return int(self) > self._coerce_value(self, other, exception_on_mismatch=False)

    @staticmethod
    def _format_legacy_ids(
        alpha_id: AlphaID,
        cutoff: int | None,
        prefix: str | None,
        separator: str | None,
        as_object: bool = False,
    ) -> str | MPID | AlphaID:
        """Format an AlphaID as either an MPID for legacy data, or AlphaID for newer data.

        Parameters
        -----------
        alpha_id : AlphaID
            An instance of AlphaID
        cutoff : int | None
            The largest legacy ID value to format as an MPID.
            If None, this returns the original AlphaID.
        prefix : str or None
            Identifier prefix
        separator : str or None
            Identifier separator. If returning an MPID and the prefix is not None,
            will override as a hyphen ("-")
        as_object : bool = False
            Whether to return objects (True) or a str (False)

        Returns
        -----------
        MPID if as_object and int(alpha_id) <= cutoff
        AlphaID if as_object and int(alpha_id) > cutoff
        str otherwise
        """
        if cutoff and ((v := int(alpha_id)) <= cutoff):
            idx = f"{prefix or ''}{'-' if prefix else ''}{v}"
            if as_object:
                return MPID(idx)
            return idx
        if as_object:
            return alpha_id
        return str(alpha_id)

    @property
    def string(self) -> str:
        """Legacy access to .string attr as in MPID."""
        return self._format_legacy_ids(
            self, self._cut_point, self._prefix, self._separator, as_object=False
        )

    @property
    def formatted(self) -> MPID | AlphaID:
        """Return an MPID for legacy indices, and AlphaID otherwise."""
        return self._format_legacy_ids(  # type: ignore[return-value]
            self, self._cut_point, self._prefix, self._separator, as_object=True
        )

    def copy(self) -> AlphaID:
        """Return a deep copy of the current instance."""
        return AlphaID(str(self))

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source: Any, handler: core_schema.CoreSchema
    ) -> core_schema.CoreSchema:
        """Generate pydantic schema for AlphaID."""
        return core_schema.with_info_plain_validator_function(cls.validate)

    @classmethod
    def __get_pydantic_json_schema__(
        cls, _core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(core_schema.str_schema())
        json_schema = handler.resolve_ref_schema(json_schema)
        json_schema["examples"] = ["mp-ft", "task:pqrs"]
        return json_schema

    @classmethod
    def validate(cls, __input_value: Any, _: core_schema.ValidationInfo) -> AlphaID:
        """Define pydantic validator for AlphaID."""
        if isinstance(__input_value, AlphaID):
            return __input_value
        elif isinstance(__input_value, str | int | MPID):
            return AlphaID(__input_value)

        raise ValueError(f"Invalid AlphaID Format {__input_value}")

    @property
    def parts(self) -> tuple[str, int]:
        """Mimic the parts attribute of MPID (prefix, integer value)."""
        return (
            self._prefix or "",
            int(self),
        )

    @property
    def next_safe(self) -> AlphaID:
        """Return the next multi-lingually "safe" AlphaID."""
        return _next_safe_alpha_id(self)


def _next_safe_alpha_id(
    start: int | str | AlphaID = 0,
) -> AlphaID:
    """Get the next "safe" (non-obscene) AlphaID.

    Returns the least AlphaID > AlphaID(start) such that its
    string value is "non-obscene".

    Uses a multi-lingual list of profanity from the shutter stock team
    (see emmet-core/dev_scripts/generate_identifier_exclude_list.py)
    to exclude generally-accepted crude language in AlphaIDs.

    Parameters
    -----------
    start : int | str | AlphaID = 0
        The AlphaID to start from.

    Returns
    -----------
    AlphaID : the next sequential AlphaID that is (mostly-)profanity free.
        (We're not perfect, there are so many languages.)
    """

    start_id = AlphaID(start) + 1
    while int(start_id) in FORBIDDEN_ALPHA_ID_VALUES:
        start_id += 1
    return start_id
