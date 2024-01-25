from enum import StrEnum


class Status(StrEnum):
    """
    State of a calculation/analysis.
    """

    SUCCESS = "successful"
    FAILED = "failed"
