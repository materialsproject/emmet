from enum import Enum, EnumMeta


class MetaEnum(EnumMeta):
    def __contains__(cls, item):
        return item in cls._value2member_map_


class ErrorMsgEnum(Enum, metaclass=MetaEnum):
    @classmethod
    def values(cls):
        return [_.value for _ in list(cls)]

    @classmethod
    def from_value(cls, value):
        return cls(value).name


class AssimilationErrors(ErrorMsgEnum):
    NO_VASP = "No VASP files found!"
    LIST_INDEX = "list index out of range"
