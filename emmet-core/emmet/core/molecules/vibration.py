import warnings
from itertools import groupby
from typing import List
from datetime import datetime

import numpy as np
from pydantic import Field

from pymatgen.core.structure import Molecule

from emmet.core.mpid import MPID
from emmet.core.structure import MoleculeMetadata
from emmet.core.material import PropertyOrigin
from emmet.core.qchem.task import TaskDocument
from emmet.core.molecules.molecule_property import PropertyDoc


class SpectrumDoc(MoleculeMetadata):
    """
    Base model definition for any spectra document. This should contain
    metadata on the structure the spectra pertains to
    """

    spectrum_name: str

    material_id: MPID = Field(
        ...,
        description="The ID of the material, used as a universal reference across proeprty documents."
        "This comes in the form: mp-******",
    )

    spectrum_id: str = Field(
        ...,
        title="Spectrum Document ID",
        description="The unique ID for this spectrum document",
    )

    last_updated: datetime = Field(
        description="Timestamp for the most recent calculation update for this property",
        default_factory=datetime.utcnow,
    )

    warnings: List[str] = Field([], description="Any warnings related to this property")


class VibSpectrumDoc(SpectrumDoc):

    spectrum_name = "IR_vibrational"

    frequencies: List[float] = Field(..., title="Vibrational Frequencies",
                                     description="List of vibrational frequencies in the molecules' spectrum")

    intensities: List[float] = Field(..., title="IR intensities",
                                     description="Intensities for IR vibrational spectrum peaks")

    task_id: MPID = Field(..., title="Calculation ID", description="Task ID used to make this IR spectrum")

    @classmethod
    def from_task(cls, task: TaskDocument, molecule_id: MPID, **kwargs): # type: ignore[override]
        """
        Construct a vibrational spectrum document

        task document from which vibrational spectrum can be extracted
        :param molecule_id: mpid
        :param kwargs: to pass to SpectrumDoc
        :return:
        """

        if task.output.frequencies is None:
            raise Exception("No frequencies in task!")

        if task.output.optimized_molecule is not None:
            mol = task.output.optimized_molecule
        else:
            mol = task.output.initial_molecule

        frequencies = task.output.frequencies
        intensities = None
        for calc in task.calcs_reversed:
            if calc.get("IR_intens", None) is not None:
                intensities = calc.get("IR_intens")
                break

        if intensities is None:
            raise Exception("No IR intensities in task!")

        return super().from_molecule(
            meta_molecule=mol,
            molecule_id=molecule_id,
            frequencies=frequencies,
            intensities=intensities,
            spectrum_id=f"{molecule_id}-IR",
            task_id=task.task_id,
            **kwargs,
        )

class VibrationDoc(PropertyDoc):

    property_name = "vibrations"

    molecule: Molecule

    frequencies: List[float] = Field(description="List of molecular vibrational frequencies")

    frequency_modes: List[List[List[float]]] = Field(description="Vibrational frequency modes of the molecule")

    spectrum: VibSpectrumDoc = Field(description="Vibrational frequency spectrum, including IR intensities")

    @classmethod
    def from_task(
        cls,
        task: TaskDocument,
        molecule_id: MPID,
        **kwargs
    ): # type: ignore[override]
        """
        Construct a vibration document from a task document

        task document from which vibrational properties can be extracted
        :param molecule_id: mpid
        :param kwargs: to pass to PropertyDoc
        :return:
        """

        if task.output.frequencies is None or task.output.frequency_modes is None:
            raise Exception("No frequencies in task!")

        if task.output.optimized_molecule is not None:
            mol = task.output.optimized_molecule
        else:
            mol = task.output.initial_molecule

        spectrum = VibSpectrumDoc.from_task(task, molecule_id=molecule_id, **kwargs)

        frequencies = task.output.frequencies
        frequency_modes =task.output.frequency_modes

        return super().from_molecule(
            meta_molecule=mol,
            molecule_id=molecule_id,
            molecule=mol,
            frequencies=frequencies,
            frequency_modes=frequency_modes,
            spectrum=spectrum,
            origins=[PropertyOrigin(name="vibrations", task_id=task.task_id)],
            **kwargs
        )