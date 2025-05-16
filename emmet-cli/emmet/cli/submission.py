from __future__ import annotations

import copy
import json
import logging
from os import PathLike
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from emmet.cli.utils import EmmetCliError
from pydantic import BaseModel, Field, PrivateAttr, model_validator
from uuid import UUID, uuid4

from emmet.core.vasp.utils import FileMetadata, recursive_discover_vasp_files

logger = logging.getLogger("emmet")


class CalculationMetadata(BaseModel):
    id: UUID = Field(
        description="The identifier for this calculation", default_factory=uuid4
    )

    files: List[FileMetadata] = Field(
        description="List of file metadata for the the files for this calculation."
    )

    calc_valid: Optional[bool] = Field(
        description="Whether calculation is valid. If None then has not been checked yet.",
        default=None,
    )

    calc_validation_errors: List[str] = Field(
        description="Validation errors for this calculation", default_factory=list
    )

    def validate_calculation(self) -> bool:
        """Validate the calculation. Returns whether it's valid."""
        self.refresh()
        if self.calc_valid is None:
            # TODO: change to do actual validation rather than just passing
            self.calc_valid = True
        return self.calc_valid

    def refresh(self) -> None:
        """Refreshes the information for the calculation (recalculates MD5s and clears validation if any changes)"""
        changed_files = False
        for f in self.files:
            cached_md5 = f._md5
            f.reset_md5()
            if cached_md5 != f.md5:
                changed_files = True
        if changed_files:
            self.calc_valid = None
            self.calc_validation_errors.clear()


class Submission(BaseModel):
    id: UUID = Field(
        description="The identifier for this submission", default_factory=uuid4
    )

    # TODO: add origin

    calculations: Dict[Path, CalculationMetadata] = Field(
        description="The calculations in this submission with the keys being the absolute paths to the directory containing the data for the calculation"
    )

    calc_history: List[Dict[Path, CalculationMetadata]] = Field(
        description="The history of pushed calculations. This gets updated whenever a new version of the calculations is pushed to the submission service",
        default_factory=list,
    )

    pending_calculations: Optional[Dict[Path, CalculationMetadata]] = Field(
        description="The calculations in this submission with the keys being the absolute paths to the directory containing the data for the calculation",
        default=None,
    )

    _pending_push: Optional[Dict[Path, FileMetadata]] = PrivateAttr(default=None)

    @model_validator(mode="before")
    def coerce_keys_to_paths(cls, data: Any) -> Any:
        if isinstance(data, dict) and "calculations" in data:
            data["calculations"] = {Path(k): v for k, v in data["calculations"].items()}
        return data

    def last_pushed(self) -> Dict[Path, CalculationMetadata] | None:
        return self.calc_history[-1] if self.calc_history else None

    def save(self, path: Path) -> None:
        """Save this submission to a JSON file."""
        path.write_text(self.model_dump_json(indent=4))

    @classmethod
    def load(
        cls, path: Path
    ) -> (
        "Submission"
    ):  # change this to use TypeVar (or self if min Python >= 3.11) if ever create subclasses
        """Load a submission from a JSON file."""
        content = path.read_text()
        data = json.loads(content)
        return cls.model_validate(data)

    @classmethod
    def from_paths(
        cls, paths: Iterable[Path]
    ) -> (
        "Submission"
    ):  # change this to use TypeVar (or self if min Python >= 3.11) if ever create subclasses
        """Create Submission from all calculations in the provided paths"""
        all_calculations = find_all_calculations(paths)
        logger.debug(f"found all calculations for {paths}:\n{all_calculations}")

        return Submission(calculations=all_calculations)

    def _merge_calculations(self, cm: dict[Path, CalculationMetadata]):
        new_calcs = {}
        keys = set(self.calculations) | set(cm)
        for k in keys:
            if k in self.calculations and k in cm:
                new_calcs[k] = CalculationMetadata(
                    id=self.calculations[k].id,
                    files=list(set(self.calculations[k].files + cm[k].files)),
                )
            else:
                tmp = self.calculations.get(k) or cm.get(k)
                assert tmp is not None
                new_calcs[k] = tmp
        self.calculations = new_calcs

    def add_to(self, paths: Iterable[Path]) -> list[FileMetadata]:
        """Add all files in the paths to the submission. Performs de-duping"""

        orig_calcs = self.calculations
        calcs_to_add = find_all_calculations(paths)
        self._merge_calculations(calcs_to_add)

        self._clear_pending()

        return list(
            set([item for cm in calcs_to_add.values() for item in cm.files])
            - set([item for cm in orig_calcs.values() for item in cm.files])
        )

    def remove_from(self, paths: Iterable[Path]) -> list[FileMetadata]:
        """Remove all files in the submission that match one of the provided paths."""

        def is_subpath(child: Path, parent: Path) -> bool:
            try:
                child.relative_to(parent)
                return True
            except ValueError:
                return False

        removed_files = []
        calculations_to_remove = set()
        files_to_remove = {}

        for calc_path, calc_metadata in self.calculations.items():
            matched_entire_calc = any(
                is_subpath(calc_path, rm_path) for rm_path in paths
            )

            if matched_entire_calc:
                calculations_to_remove.add(calc_path)
                removed_files.extend(calc_metadata.files)
                continue  # Skip checking individual files if whole calc is removed

            # Check individual files
            matching_files = [
                fm
                for fm in calc_metadata.files
                if any(is_subpath(fm.path, rm_path) for rm_path in paths)
            ]
            if matching_files:
                files_to_remove[calc_path] = matching_files
                removed_files.extend(matching_files)

        # Remove entire calculations
        for path in calculations_to_remove:
            self.calculations.pop(path, None)

        # Remove matching files from remaining calculations
        for path, files in files_to_remove.items():
            remaining_files = [
                fm for fm in self.calculations[path].files if fm not in files
            ]
            self.calculations[path].files = remaining_files

        self._clear_pending()

        return removed_files

    def validate_submission(self) -> bool:
        is_valid = True
        calcs_to_check = (
            self.pending_calculations
            if self.pending_calculations
            else self.calculations
        )

        for p, cm in calcs_to_check.items():
            is_valid = cm.validate_calculation() and is_valid

        return is_valid

    def _create_refreshed_calculations(self):
        pending_calculations = copy.deepcopy(self.calculations)
        for cm in pending_calculations.values():
            cm.refresh()
        return pending_calculations

    def stage_for_push(self) -> List[FileMetadata]:
        """ "Stages submission for push. Returns the list of files that will need to be (re)pushed."""
        self.pending_calculations = self._create_refreshed_calculations()

        if not self.validate_submission():
            assert self.pending_calculations is not None
            self.calculations = copy.deepcopy(self.pending_calculations)
            self._clear_pending()
            raise EmmetCliError(
                "Submission does not pass validation. Please fix validation errors prior to staging."
            )

        changes = self.get_changed_files_per_calc_path(
            self.last_pushed(), self.pending_calculations
        )
        self._pending_push = changes

        return [item for sublist in changes.values() for item in sublist]

    def get_changed_files_per_calc_path(self, previous, current):
        changes = {}
        if not previous:
            changes = {k: v.files for k, v in current.items()}
        else:
            for p, cm in current.items():
                if p not in previous.keys():
                    changes[p] = cm.files
                else:
                    file_changes = []
                    for fm in cm.files:
                        match = next(
                            (item for item in previous[p].files if item == fm), None
                        )
                        if match is None or fm.md5 != match.md5:
                            file_changes.append(fm)
                    if file_changes:
                        changes[p] = file_changes
        return changes

    def push(self):  ## TODO: return type
        """Performs the push. Returns info about the push"""
        if not self.pending_calculations:
            raise EmmetCliError("Nothing is staged. Please stage before pushing.")

        if self.get_changed_files_per_calc_path(
            self.pending_calculations, self._create_refreshed_calculations()
        ):
            raise EmmetCliError(
                "Files for submission have changed since staging. Please re-stage before pushing."
            )

        if not self.validate_submission():  # THIS SHOULD NEVER HAPPEN
            self.calculations = copy.deepcopy(self.pending_calculations)
            self._clear_pending()
            raise EmmetCliError(
                "Submission does not pass validation. Please fix validation errors and re-stage."
            )

        # TODO: do push
        for k, _ in self._pending_push.items():
            # call RawArchive static method to create file_paths from list of FileMetadata for the pending_calc[k]
            # construct a RawArchive file for writing
            # push that file to S3
            pass

        # do bookkeeping
        self.calc_history.append(self.pending_calculations)
        self._clear_pending()

    def _clear_pending(self):
        self.pending_calculations = None
        self._pending_push = None


def find_all_calculations(paths: Iterable[PathLike]):
    all_calculations = {}
    for path in paths:
        path = Path(path).resolve()
        if path.is_dir():
            calcs = recursive_discover_vasp_files(path)
            all_calculations.update(calcs)
        else:
            parent = path.parent
            fm = FileMetadata(name=path.name, path=path)
            if parent in all_calculations:
                if fm not in all_calculations[parent]:
                    all_calculations[parent].append(fm)
            else:
                all_calculations[parent] = [fm]

    return {k: CalculationMetadata(files=v) for k, v in all_calculations.items()}
