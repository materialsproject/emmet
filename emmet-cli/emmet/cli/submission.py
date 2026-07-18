from __future__ import annotations

import copy
import json
import logging
from collections import defaultdict
from multiprocessing import get_context
from os import PathLike, cpu_count
from pathlib import Path
from typing import ClassVar, Iterable, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, PrivateAttr

from emmet.cli.utils import EmmetCliError
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
        description="List of file metadata for the files for this calculation."
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
        try:
            self.refresh()
            if self.calc_valid is None:
                logger.debug(f"Validating calculation at {locator.path}")
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
            changed_files |= cached_hash != f.hash
        if changed_files:
            self.calc_valid = None
            self.calc_validation_errors.clear()


class CalculationChange(BaseModel):
    """A calculation-level change included in a submission snapshot."""

    calculation_id: UUID
    status: Literal["added", "changed", "removed"]
    locator: CalculationLocator
    calculation: CalculationMetadata | None = None
    added_files: list[str] = Field(default_factory=list)
    changed_files: list[str] = Field(default_factory=list)
    removed_files: list[str] = Field(default_factory=list)


class SubmissionChangeSet(BaseModel):
    """The complete set of changes between two submission snapshots."""

    current_calculations: list[tuple[CalculationLocator, CalculationMetadata]]
    changes: list[CalculationChange]

    @property
    def has_changes(self) -> bool:
        return bool(self.changes)


class SubmissionUploader(Protocol):
    """Upload a staged submission snapshot to a remote service."""

    def upload(self, submission_id: UUID, changes: SubmissionChangeSet) -> None: ...


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
    ITEMS_PER_OUTER_CHUNK: ClassVar[int] = 4 * PARALLEL_THRESHOLD

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
        description="The calculations pending a push in this submission as a list of (locator, metadata) tuples",
        default=None,
    )

    _pending_push: SubmissionChangeSet | None = PrivateAttr(default=None)

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

        removed_files = []
        calculations_to_remove = set()
        files_to_remove = {}

        for calc_locator, calc_metadata in self.calculations:
            matched_entire_calc = any(
                calc_locator.path.is_relative_to(rm_path) for rm_path in paths
            )

            if matched_entire_calc:
                calculations_to_remove.add(calc_locator)
                removed_files.extend(calc_metadata.files)
                continue  # Skip checking individual files if whole calc is removed

            # Check individual files
            matching_files = [
                fm
                for fm in calc_metadata.files
                if any(fm.path.is_relative_to(rm_path) for rm_path in paths)
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

        total_items = len(calcs_to_check)
        chunk_size = Submission.ITEMS_PER_OUTER_CHUNK

        def num_procs():
            num_processes = 1
            if cpu_count() > 100:
                num_processes = 100
            else:
                num_processes = cpu_count()
            logger.debug(f"Recommending {num_processes} for pool size.")
            return num_processes

        if total_items > Submission.PARALLEL_THRESHOLD:
            logger.debug(
                f"Running validation in parallel for {total_items} calculations "
                f"splitting into {len(calcs_to_check)/chunk_size}"
            )
            ctx = get_context("fork")
            for i in range(0, total_items, chunk_size):
                chunk = calcs_to_check[i : i + chunk_size]
                logger.debug(
                    f"Processing chunk {i//chunk_size + 1}: items {i}-{min(i+chunk_size, total_items)}"
                )

                with ctx.Pool(processes=num_procs()) as pool:
                    results = pool.imap_unordered(invoke_calc_validation, chunk)
                    processed = 0
                    for locator, _, cm in results:
                        # Update the calculation metadata in the list
                        for j, (loc, _) in enumerate(chunk):
                            if loc == locator:
                                calcs_to_check[i + j] = (loc, cm)
                        processed += 1
                    logger.debug(f"Completed processing {processed} calculation")
            return all(cm.calc_valid for _, cm in calcs_to_check)
        else:
            logger.debug(f"Running validation serially for {total_items} calculations")
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
                ctx = get_context("fork")
                with ctx.Pool(processes=cpu_count()) as pool:
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

    def stage_for_push(self) -> SubmissionChangeSet:
        """Stage and validate the current snapshot for a remote push."""
        self.pending_calculations = self._create_calculations_copy()

        if not self.validate_submission():
            assert self.pending_calculations is not None
            self.calculations = copy.deepcopy(self.pending_calculations)
            self._clear_pending()
            raise EmmetCliError(
                "Submission does not pass validation. Please fix validation errors prior to staging."
            )

        self._pending_push = self.get_submission_changes(
            self.last_pushed(), self.pending_calculations
        )
        return self._pending_push

    def get_submission_changes(
        self,
        previous: list[tuple[CalculationLocator, CalculationMetadata]] | None,
        current: list[tuple[CalculationLocator, CalculationMetadata]],
    ) -> SubmissionChangeSet:
        """Return added, changed, and removed calculations and files."""
        previous_by_id = {
            calculation.id: (locator, calculation)
            for locator, calculation in (previous or [])
        }
        current_by_id = {
            calculation.id: (locator, calculation) for locator, calculation in current
        }
        changes = []

        for calculation_id in sorted(current_by_id, key=str):
            locator, calculation = current_by_id[calculation_id]
            previous_entry = previous_by_id.get(calculation_id)
            current_files = {file.name: file for file in calculation.files}

            if previous_entry is None:
                changes.append(
                    CalculationChange(
                        calculation_id=calculation_id,
                        status="added",
                        locator=locator,
                        calculation=calculation,
                        added_files=sorted(current_files),
                    )
                )
                continue

            _, previous_calculation = previous_entry
            previous_files = {file.name: file for file in previous_calculation.files}
            added_files = sorted(current_files.keys() - previous_files.keys())
            removed_files = sorted(previous_files.keys() - current_files.keys())
            changed_files = sorted(
                name
                for name in current_files.keys() & previous_files.keys()
                if current_files[name].hash != previous_files[name].hash
            )
            if added_files or changed_files or removed_files:
                changes.append(
                    CalculationChange(
                        calculation_id=calculation_id,
                        status="changed",
                        locator=locator,
                        calculation=calculation,
                        added_files=added_files,
                        changed_files=changed_files,
                        removed_files=removed_files,
                    )
                )

        for calculation_id in sorted(
            previous_by_id.keys() - current_by_id.keys(), key=str
        ):
            locator, calculation = previous_by_id[calculation_id]
            changes.append(
                CalculationChange(
                    calculation_id=calculation_id,
                    status="removed",
                    locator=locator,
                    removed_files=sorted(file.name for file in calculation.files),
                )
            )

        return SubmissionChangeSet(
            current_calculations=current,
            changes=changes,
        )

    def push(self, uploader: SubmissionUploader) -> None:
        """Performs the push. Returns info about the push"""
        if (
            self.pending_calculations is None
            or self._pending_push is None
            or not self._pending_push.has_changes
        ):
            raise EmmetCliError("Nothing is staged. Please stage before pushing.")

        current = self._create_calculations_copy(refresh=True)
        if self.get_submission_changes(self.pending_calculations, current).has_changes:
            raise EmmetCliError(
                "Files for submission have changed since staging. Please re-stage before pushing."
            )

        if not self.validate_submission():  # THIS SHOULD NEVER HAPPEN
            self.calculations = copy.deepcopy(self.pending_calculations)
            self._clear_pending()
            raise EmmetCliError(
                "Submission does not pass validation. Please fix validation errors and re-stage."
            )

        uploader.upload(self.id, self._pending_push)

        # do bookkeeping
        self.calc_history.append(self.pending_calculations)
        self._clear_pending()

    def _clear_pending(self):
        self.pending_calculations = None
        self._pending_push = None


def find_all_calculations(paths: Iterable[PathLike]):
    all_calculations: dict[CalculationLocator, list[FileMetadata]] = defaultdict(list)
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
            if fm not in all_calculations[locator]:
                all_calculations[locator].append(fm)

    return [(k, CalculationMetadata(files=v)) for k, v in all_calculations.items()]
