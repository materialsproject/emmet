from emmet.core.utils import ValueEnum


class Status(ValueEnum):
    """
    State of a calculation/analysis.
    """

    SUCCESS = "successful"
    FAILED = "failed"
