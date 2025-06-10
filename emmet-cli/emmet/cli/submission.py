from __future__ import annotations

import copy
import json
import logging
from multiprocessing import Pool
from os import PathLike
from pathlib import Path
from typing import Any, ClassVar, Dict, Iterable, List, Optional
from emmet.cli.utils import EmmetCliError
from pydantic import BaseModel, Field, PrivateAttr, model_validator
from uuid import UUID, uuid4

from emmet.core.vasp.utils import FileMetadata, recursive_discover_vasp_files
from pymatgen.io.validation.validation import VaspValidator

logger = logging.getLogger("emmet")


class CalculationLocator(BaseModel):
    model_config = {"exclude_none": True}

    path: Path = Field(description="The path to the calculation directory")
    modifier: Optional[str] = Field(
        description="Optional modifier for the calculation", default=None
    )

    def __hash__(self) -> int:
        # Resolve path to handle different representations of same path
        return hash((self.path.resolve(), self.modifier))

    # You might not need custom __eq__ in Pydantic v2
    # But if you keep it, consider path resolution:
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, CalculationLocator):
            return False
        return (
            self.path.resolve() == other.path.resolve()
            and self.modifier == other.modifier
        )


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

    def validate_calculation(self, locator: CalculationLocator) -> bool:
        """Validate the calculation. Returns whether it's valid."""
        self.refresh()
        if self.calc_valid is None:
            # print(f"Validating calculation at {locator.path}")
            # validator = VaspValidator.from_directory(dir_name=locator.path, fast=True) # TODO: add modifier
            # self.calc_valid = validator.valid
            # self.calc_validation_errors = validator.reasons
            self.calc_valid = True
        return self.calc_valid

    def refresh(self) -> None:
        """Refreshes the information for the calculation (recalculates hashes and clears validation if any changes)"""
        changed_files = False
        for f in self.files:
            cached_hash = f.hash
            f.compute_hash()
            if cached_hash != f.hash:
                changed_files = True
        if changed_files:
            self.calc_valid = None
            self.calc_validation_errors.clear()


def invoke_calc_refresh(args):
    path, cm = args
    cm.refresh()
    return path, cm


def invoke_calc_validation(args):
    locator, cm = args
    valid = cm.validate_calculation(locator)
    return locator, valid, cm


class Submission(BaseModel):
    PARALLEL_THRESHOLD: ClassVar[int] = 100

    id: UUID = Field(
        description="The identifier for this submission", default_factory=uuid4
    )

    # TODO: add origin

    calculations: Dict[CalculationLocator, CalculationMetadata] = Field(
        description="The calculations in this submission with the keys being the locators for the calculations"
    )

    calc_history: List[Dict[CalculationLocator, CalculationMetadata]] = Field(
        description="The history of pushed calculations. This gets updated whenever a new version of the calculations is pushed to the submission service",
        default_factory=list,
    )

    pending_calculations: Optional[Dict[CalculationLocator, CalculationMetadata]] = (
        Field(
            description="The calculations in this submission with the keys being the locators for the calculations",
            default=None,
        )
    )

    _pending_push: Optional[Dict[CalculationLocator, FileMetadata]] = PrivateAttr(
        default=None
    )

    @model_validator(mode="before")
    def coerce_keys_to_locators(cls, data: Any) -> Any:
        if isinstance(data, dict) and "calculations" in data:
            new_calcs = {}
            for k, v in data["calculations"].items():
                if isinstance(k, str):
                    # Handle string representation of CalculationLocator
                    if k.startswith("path="):
                        # Parse the string representation
                        path_str = k.split("path=")[1].split(" modifier=")[0]
                        # Clean up nested PosixPath strings
                        while "PosixPath(" in path_str:
                            path_str = path_str.split("PosixPath(")[1].rstrip(")")
                        # Remove any remaining quotes
                        path_str = path_str.strip("'\"")
                        modifier = None
                        if "modifier=" in k:
                            mod_str = k.split("modifier=")[1]
                            # Only set modifier if it's not the string "None"
                            if mod_str != "None":
                                modifier = mod_str
                        new_calcs[
                            CalculationLocator(path=Path(path_str), modifier=modifier)
                        ] = v
                    else:
                        # Handle simple path string
                        new_calcs[CalculationLocator(path=Path(k))] = v
                else:
                    new_calcs[k] = v
            data["calculations"] = new_calcs
        return data

    def last_pushed(self) -> Dict[CalculationLocator, CalculationMetadata] | None:
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

    def _merge_calculations(self, cm: dict[CalculationLocator, CalculationMetadata]):
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

        for calc_locator, calc_metadata in self.calculations.items():
            matched_entire_calc = any(
                is_subpath(calc_locator.path, rm_path) for rm_path in paths
            )

            if matched_entire_calc:
                calculations_to_remove.add(calc_locator)
                removed_files.extend(calc_metadata.files)
                continue  # Skip checking individual files if whole calc is removed

            # Check individual files
            matching_files = [
                fm
                for fm in calc_metadata.files
                if any(is_subpath(fm.path, rm_path) for rm_path in paths)
            ]
            if matching_files:
                files_to_remove[calc_locator] = matching_files
                removed_files.extend(matching_files)

        # Remove entire calculations
        for locator in calculations_to_remove:
            self.calculations.pop(locator, None)

        # Remove matching files from remaining calculations
        for locator, files in files_to_remove.items():
            remaining_files = [
                fm for fm in self.calculations[locator].files if fm not in files
            ]
            self.calculations[locator].files = remaining_files

        self._clear_pending()

        return removed_files

    def validate_submission(self, check_all: bool = False) -> bool:
        is_valid = True
        calcs_to_check = (
            self.pending_calculations
            if self.pending_calculations
            else self.calculations
        )

        if len(calcs_to_check) > Submission.PARALLEL_THRESHOLD:
            logger.debug(
                f"Running validation in parallel for {len(calcs_to_check)} calculations"
            )
            with Pool() as pool:
                results = pool.map(invoke_calc_validation, calcs_to_check.items())
                for locator, _, cm in results:
                    calcs_to_check[locator] = cm
                return all(val for _, val, _ in results)
        else:
            logger.debug(
                f"Running validation serially for {len(calcs_to_check)} calculations"
            )
            if not check_all:
                logger.debug("Will fail fast if any calculation is invalid")
            for locator, cm in calcs_to_check.items():
                is_valid = cm.validate_calculation(locator) and is_valid
                if not is_valid and not check_all:
                    return is_valid

            return is_valid

    def _create_calculations_copy(self, refresh: bool = False):
        pending_calculations = copy.deepcopy(self.calculations)
        if refresh:
            if len(pending_calculations) > Submission.PARALLEL_THRESHOLD:
                logger.debug(
                    f"Running refresh in parallel for {len(pending_calculations)} calculations"
                )
                with Pool() as pool:
                    results = pool.map(
                        invoke_calc_refresh,
                        [
                            (locator.path, cm)
                            for locator, cm in pending_calculations.items()
                        ],
                    )
                    for p, cm in results:
                        pending_calculations[CalculationLocator(path=p)] = cm
            else:
                logger.debug(
                    f"Running refresh serially for {len(pending_calculations)} calculations"
                )
                for cm in pending_calculations.values():
                    cm.refresh()
        return pending_calculations

    def stage_for_push(self) -> List[FileMetadata]:
        """Stages submission for push. Returns the list of files that will need to be (re)pushed."""
        self.pending_calculations = self._create_calculations_copy()

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
                        if match is None or fm.hash != match.hash:
                            file_changes.append(fm)
                    if file_changes:
                        changes[p] = file_changes
        return changes

    def push(self):  ## TODO: return type
        """Performs the push. Returns info about the push"""
        if not self.pending_calculations:
            raise EmmetCliError("Nothing is staged. Please stage before pushing.")

        if self.get_changed_files_per_calc_path(
            self.pending_calculations, self._create_calculations_copy(refresh=True)
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
        logger.info(f"Checking path: {path}")
        if path.is_dir():
            calcs = recursive_discover_vasp_files(path)
            all_calculations.update(
                {CalculationLocator(path=k): v for k, v in calcs.items()}
            )
        else:
            parent = path.parent
            fm = FileMetadata(name=path.name, path=path)
            locator = CalculationLocator(path=parent)
            if locator in all_calculations:
                if fm not in all_calculations[locator]:
                    all_calculations[locator].append(fm)
            else:
                all_calculations[locator] = [fm]

    return {k: CalculationMetadata(files=v) for k, v in all_calculations.items()}
