"""Code agnostic archival tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import Field
from pathlib import Path

from emmet.archival.base import Archiver

if TYPE_CHECKING:
    pass


class FileArchive(Archiver):
    """Class supporting generic file archiving."""

    files: list[Path] = Field(description="The file paths to include.")

    @staticmethod
    def _get_path_relative_to_parent(path: Path, parent: Path) -> Path:
        if not path.is_relative_to(parent):
            raise ValueError(f"Path {path} is not relative to {parent}")
        for p in path.parents:
            if p == parent:
                break
        leaf = str(path).split(str(p), 1)[1]
        if leaf.startswith("/"):
            leaf = "." + leaf
        return Path(leaf)

    # @classmethod
    # def from_directory(
    #     cls,
    #     dir_name : str | Path,
    #     depth : int | None = 1,
    # ) -> Self:

    #     cdir = Path(dir_name)
    #     for fsobj in os.scandir(cdir):
