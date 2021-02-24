from dataclasses import dataclass
from typing import Union

NOTHING = object()


class MPID(str):
    """
    A Materials Project type ID with a prefix and an integer
    This class enables seemlessly mixing MPIDs and regular integer IDs
    Prefixed IDs are considered less than non-prefixed IDs to enable proper
    mixing with the Materials Project
    """

    def __lt__(self, other: Union["MPID", int, str]):

        # Always sort MPIDs before pure integer IDs
        if isinstance(other, int):
            return True

        self_parts = self.split("-")
        other_parts = other.split("-")

        return self_parts < other_parts
