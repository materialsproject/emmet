from __future__ import annotations

import copy
import json
import logging
from multiprocessing import Pool
from os import PathLike
from pathlib import Path
from typing import ClassVar, Iterable
from emmet.cli.utils import EmmetCliError
from pydantic import BaseModel, Field, PrivateAttr
from uuid import UUID, uuid4

from emmet.core.vasp.utils import (
    CalculationLocator,
    FileMetadata,
    recursive_discover_vasp_files,
)

from emmet.core.vasp.validation import ValidationDoc

logger = logging.getLogger("emmet")


class CalculationMetadata(BaseModel):
    id: UUID = Field(
        description="The identifier for this calculation", default_factory=uuid4
    )

    files: list[FileMetadata] = Field(
        description="List of file metadata for the the files for this calculation."
    )

    calc_valid: bool | None = Field(
        description="Whether calculation is valid. If None then has not been checked yet.",
        default=None,
    )

    calc_validation_errors: list[str] = Field(
        description="Validation errors for this calculation", default_factory=list
    )

    def validate_calculation(self, locator: CalculationLocator) -> bool:
        """Validate the calculation. Returns whether it's valid."""
        self.refresh()
        if self.calc_valid is None:
            logger.debug(f"Validating calculation at {locator.path}")
            try:
                validator = ValidationDoc.from_file_metadata(
                    file_meta=self.files, fast=True
                )
                self.calc_valid = validator.valid
                self.calc_validation_errors = validator.reasons
            except Exception as e:
                logger.info(f"Error validating calculation: {str(e)}")
                self.calc_valid = False
                self.calc_validation_errors.append(
                    f"Error validating calculation: {str(e)}"
                )
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

    calculations: list[tuple[CalculationLocator, CalculationMetadata]] = Field(
        description="The calculations in this submission as a list of (locator, metadata) tuples"
    )

    calc_history: list[list[tuple[CalculationLocator, CalculationMetadata]]] = Field(
        description="The history of pushed calculations as a list of lists of (locator, metadata) tuples. This gets updated whenever a new version of the calculations is pushed to the submission service",
        default_factory=list,
    )

    pending_calculations: (
        list[tuple[CalculationLocator, CalculationMetadata]] | None
    ) = Field(
        description="The calculations in this submission as a list of (locator, metadata) tuples",
        default=None,
    )

    _pending_push: dict[CalculationLocator, FileMetadata] | None = PrivateAttr(
        default=None
    )

    def last_pushed(
        self,
    ) -> list[tuple[CalculationLocator, CalculationMetadata]] | None:
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

    def _merge_calculations(
        self, cm: list[tuple[CalculationLocator, CalculationMetadata]]
    ):
        new_calcs = []
        existing_keys = {k for k, _ in self.calculations}
        new_keys = {k for k, _ in cm}
        keys = existing_keys | new_keys

        for k in keys:
            existing_calc = next((v for loc, v in self.calculations if loc == k), None)
            new_calc = next((v for loc, v in cm if loc == k), None)

            if existing_calc and new_calc:
                new_calcs.append(
                    (
                        k,
                        CalculationMetadata(
                            id=existing_calc.id,
                            files=list(set(existing_calc.files + new_calc.files)),
                        ),
                    )
                )
            else:
                tmp = existing_calc or new_calc
                assert tmp is not None
                new_calcs.append((k, tmp))
        self.calculations = new_calcs

    def add_to(self, paths: Iterable[Path]) -> list[FileMetadata]:
        """Add all files in the paths to the submission. Performs de-duping"""
        orig_calcs = self.calculations
        calcs_to_add = find_all_calculations(paths)
        self._merge_calculations(calcs_to_add)

        self._clear_pending()

        return list(
            set([item for _, cm in calcs_to_add for item in cm.files])
            - set([item for _, cm in orig_calcs for item in cm.files])
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

        for calc_locator, calc_metadata in self.calculations:
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

        # Remove entire calculations and update files
        self.calculations = [
            (loc, cm)
            for loc, cm in self.calculations
            if loc not in calculations_to_remove
        ]

        # Remove matching files from remaining calculations
        for locator, files in files_to_remove.items():
            for i, (loc, cm) in enumerate(self.calculations):
                if loc == locator:
                    remaining_files = [fm for fm in cm.files if fm not in files]
                    self.calculations[i] = (
                        loc,
                        CalculationMetadata(id=cm.id, files=remaining_files),
                    )

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
                results = pool.imap_unordered(
                    invoke_calc_validation, calcs_to_check, chunksize=10
                )
                processed = 0
                for locator, _, cm in results:
                    # Update the calculation metadata in the list
                    for i, (loc, _) in enumerate(calcs_to_check):
                        if loc == locator:
                            calcs_to_check[i] = (loc, cm)
                    processed += 1
                if processed <= 10 or processed % 100 == 0:
                    logger.debug(
                        f"Processed {processed}/{len(calcs_to_check)} calculations "
                    )
                logger.debug(f"Completed processing {processed} calculation")
                return all(val for _, val, _ in results)
        else:
            logger.debug(
                f"Running validation serially for {len(calcs_to_check)} calculations"
            )
            if not check_all:
                logger.debug("Will fail fast if any calculation is invalid")
            for i, (locator, cm) in enumerate(calcs_to_check):
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
                        [(locator.path, cm) for locator, cm in pending_calculations],
                    )
                    for p, cm in results:
                        # Update the calculation metadata in the list
                        for i, (loc, _) in enumerate(pending_calculations):
                            if loc.path == p:
                                pending_calculations[i] = (loc, cm)
            else:
                logger.debug(
                    f"Running refresh serially for {len(pending_calculations)} calculations"
                )
                for i, (_, cm) in enumerate(pending_calculations):
                    cm.refresh()
        return pending_calculations

    def stage_for_push(self) -> list[FileMetadata]:
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

    def get_changed_files_per_calc_path(
        self,
        previous: list[tuple[CalculationLocator, CalculationMetadata]] | None,
        current: list[tuple[CalculationLocator, CalculationMetadata]],
    ) -> dict[CalculationLocator, list[FileMetadata]]:
        changes: dict[CalculationLocator, list[FileMetadata]] = {}
        if not previous:
            changes = {k: v.files for k, v in current}
        else:
            for loc, cm in current:
                prev_cm = next((cm_p for loc_p, cm_p in previous if loc_p == loc), None)
                if prev_cm is None:
                    changes[loc] = cm.files
                else:
                    file_changes = []
                    for fm in cm.files:
                        match = next(
                            (item for item in prev_cm.files if item == fm), None
                        )
                        if match is None or fm.hash != match.hash:
                            file_changes.append(fm)
                    if file_changes:
                        changes[loc] = file_changes
        return changes

    def push(self) -> None:
        """Performs the push. Returns info about the push"""
        if not self.pending_calculations or not self._pending_push:
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
            all_calculations.update(calcs)
        else:
            parent = path.parent
            fm = FileMetadata(name=path.name, path=path)
            locator = CalculationLocator(path=parent, modifier=fm.calc_suffix)
            if locator in all_calculations:
                if fm not in all_calculations[locator]:
                    all_calculations[locator].append(fm)
            else:
                all_calculations[locator] = [fm]

    return [(k, CalculationMetadata(files=v)) for k, v in all_calculations.items()]
