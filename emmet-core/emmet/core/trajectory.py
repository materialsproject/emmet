"""Define schemas for trajectories."""
from __future__ import annotations

from enum import Enum
import numpy as np
from pydantic import BaseModel, Field
from pathlib import Path
from typing import TYPE_CHECKING

from pymatgen.core import Element, Structure
from pymatgen.core.trajectory import Trajectory as PmgTrajectory

from monty.dev import requires
from monty.serialization import dumpfn

from emmet.core.math import Vector3D, Matrix3D
from emmet.core.tasks import TaskDoc
from emmet.core.vasp.calculation import ElectronicStep

try:
    import pyarrow as pa
    import pyarrow.parquet as pa_pq
    from pyarrow import Table as ArrowTable

except ImportError:
    pa = None
    pa_pq = None
    ArrowTable = None

if TYPE_CHECKING:
    from typing_extensions import Self
    from collections.abc import Sequence


class TrajFormat(Enum):
    """Define known trajectory formats."""

    PMG = "json"
    ASE = "traj"
    PARQUET = "parquet"


class Trajectory(BaseModel):
    """Low memory schema for trajectories that can interface with parquet, pymatgen, and ASE."""

    elements: list[int] = Field(
        description="The proton number Z of the elements in the sites"
    )

    cart_coords: list[list[Vector3D]] = Field(
        description="The Cartesian coordinates (Å) of the sites at each ionic step"
    )
    num_ionic_steps: int = Field(description="The number of ionic steps.")

    constant_lattice: Matrix3D | None = Field(
        None,
        description="The constant lattice throughout the trajectory. If not populated, it is assumed that the lattice varies.",
    )
    lattice: list[Matrix3D] | None = Field(
        None,
        description="The lattice at each ionic step. If not populated, it is assumed the lattice is constant through the trajectory.",
    )

    electronic_steps: list[list[ElectronicStep]] | None = Field(
        None, description="The electronic steps within a given ionic step."
    )
    num_electronic_steps: list[int] | None = Field(
        None, description="The number of electronic steps within each ionic step."
    )

    energy: list[float] | None = Field(
        None,
        description="The total energy in eV at each ionic step. This key is also called e_0_energy.",
    )
    e_wo_entrp: list[float] | None = Field(
        None,
        description="The total energy in eV without electronic pseudoentropy from smearing of the Fermi surface.",
    )
    e_fr_energy: list[float] | None = Field(
        None, description="The total electronic free energy in eV."
    )
    forces: list[list[Vector3D]] | None = Field(
        None, description="The interatomic forces in eV/Å at each ionic step."
    )
    stress: list[Matrix3D] | None = Field(
        None, description="The 3x3 stress tensor in kilobar at each ionic step."
    )

    identifier: str | None = Field(
        None, description="Identifier of this trajectory, e.g., task ID."
    )

    def __hash__(self) -> int:
        """Used to verify roundtrip conversion of Trajectory."""
        return hash(self.model_dump_json())

    @staticmethod
    def reorder_structure(structure: Structure, ref_z: list[int]) -> Structure:
        """
        Ensure that the sites in a structure match the order in a set of reference Z values.

        Quick returns if the structure already matches the reference order.

        Parameters
        -----------
        structure : pymatgen .Structure
            Structure to order sites in
        ref_z : list of int
            List of proton numbers / Z values in the reference structure.

        Returns
        -----------
        pymatgen .Structure : structure matching the reference order of sites
        """
        if [site.species.elements[0].Z for site in structure] == ref_z:
            return structure

        running_sites = list(range(len(structure)))
        ordered_sites = []
        for z in ref_z:
            for idx in running_sites:
                if structure[idx].species.elements[0].Z == z:
                    ordered_sites.append(structure[idx])
                    running_sites.remove(idx)
                    break

        if len(running_sites) > 0:
            raise ValueError("Cannot order structure according to reference list.")

        return Structure.from_sites(ordered_sites)

    @classmethod
    def _from_dict(
        cls,
        props: dict[str, list],
        constant_lattice: bool = False,
        lattice_match_tol: float | None = 1.0e-6,
        **kwargs,
    ) -> Self:
        """
        Common class constructor to create a Trajectory from a dict.

        Parameters
        -----------
        props : dict of str to list
            Dictionary with keys in cls.model_fields and values which are lists
        constant_lattice : bool (default = False)
            Whether the lattice is constant thoughout the trajectory
        lattice_match_tol : float or None (default = 1e-6)
            If a float and constant_lattice is False, this defines the tolerance
            for determining if the lattice has changed during the course of the
            trajectory. If None, no check is performed.
        **kwargs
            Other kwargs to pass to Trajectory

        Returns
        -----------
        Trajectory
        """
        structures = props.pop("structure")
        if any(not structure.is_ordered for structure in structures):
            raise ValueError(
                "At this time, the Trajectory model in emmet does not support disordered structures."
            )

        num_ionic_steps = len(structures)

        props["elements"] = [site.species.elements[0].Z for site in structures[0]]
        if constant_lattice or (
            lattice_match_tol
            and all(
                np.all(
                    np.abs(structures[i].lattice.matrix - structures[j].lattice.matrix)
                    < lattice_match_tol
                )
                for i in range(num_ionic_steps)
                for j in range(i + 1, num_ionic_steps)
            )
        ):
            props["constant_lattice"] = structures[0].lattice.matrix
        else:
            props["lattice"] = [structure.lattice.matrix for structure in structures]

        props["cart_coords"] = [
            cls.reorder_structure(structure, props["elements"]).cart_coords
            for structure in structures
        ]

        if len(esteps := props.get("electronic_steps", [])) > 0:
            props["num_electronic_steps"] = [len(estep) for estep in esteps]

        return cls(**props, num_ionic_steps=num_ionic_steps, **kwargs)

    @classmethod
    def from_task_doc(cls, task_doc: TaskDoc, **kwargs) -> Self:
        """
        Create a trajectory from a TaskDoc.

        Parameters
        -----------
        task_doc : emmet.core.TaskDoc
        constant_lattice : bool (default = False)
            Whether the lattice is constant thoughout the trajectory
        kwargs
            Other kwargs to pass to Trajectory

        Returns
        -----------
        Trajectory
        """
        props: dict[str, list] = {
            "structure": [],
            "cart_coords": [],
            "electronic_steps": [],
            "energy": [],
            "e_wo_entrp": [],
            "e_fr_energy": [],
            "forces": [],
            "stress": [],
        }
        # un-reverse the calcs_reversed
        for cr in task_doc.calcs_reversed[::-1]:
            for ionic_step in cr.output.ionic_steps:
                props["structure"].append(ionic_step.structure)

                props["energy"].append(ionic_step.e_0_energy)
                for k in (
                    "e_fr_energy",
                    "e_wo_entrp",
                    "forces",
                    "stress",
                    "electronic_steps",
                ):
                    props[k].append(getattr(ionic_step, k))

        return cls._from_dict(props, identifier=task_doc.task_id.string, **kwargs)

    @classmethod
    def from_pmg(cls, traj: PmgTrajectory, **kwargs) -> Self:
        """
        Create a trajectory from a pymatgen .Trajectory.

        Parameters
        -----------
        traj : pymatgen.core.trajectory.Trajectory
        constant_lattice : bool (default = False)
            Whether the lattice is constant thoughout the trajectory
        lattice_match_tol : float or None (default = 1e-6)
            If a float and constant_lattice is False, this defines the tolerance
            for determining if the lattice has changed during the course of the
            trajectory. If None, no check is performed.

        Returns
        -----------
        Trajectory
        """
        props: dict[str, list] = {
            "structure": [structure for structure in traj],
        }
        if traj.frame_properties:
            for k in cls.model_fields:
                vals = [fp.get(k) for fp in traj.frame_properties]
                if all(v is not None for v in vals):
                    props[k] = vals

        return cls._from_dict(props, **kwargs)

    @requires(
        pa is not None, message="pyarrow must be installed to de-/serialize to parquet"
    )
    def to_arrow(
        self, file_name: str | Path | None = None, **write_file_kwargs
    ) -> ArrowTable:
        """
        Create a PyArrow Table from a Trajectory.

        Parameters
        -----------
        file_name : str, .Path, or None (default)
            If not None, a file to write the parquet-format output to.
            Accepts any compression extension used by pyarrow.write_table
        **write_file_kwargs
            If file_name is not None, any kwargs to pass to
            pyarrow.parquet.write_file

        Returns
        -----------
        pyarrow.Table
        """
        pa_config = {
            k: pa.array(v)
            for k, v in self.model_dump(mode="json").items()
            if hasattr(v, "__len__") and not isinstance(v, str)
        }
        pa_config["elements"] = pa.array(
            [self.elements for _ in range(self.num_ionic_steps)]
        )
        pa_config["identifier"] = pa.array(
            [self.identifier for _ in range(self.num_ionic_steps)]
        )

        pa_table = pa.table(pa_config)
        if file_name:
            pa_pq.write_table(pa_table, file_name, **write_file_kwargs)

        return pa_table

    @classmethod
    def from_parquet(cls, file_name: str | Path, identifier: str | None = None) -> Self:
        """
        Create a trajectory from a parquet file.

        Parameters
        -----------
        file_name : str or .Path
            The parquet file to read from
        identifier : str or None (default)
            If not None, the identifier of the trajectory to return
            from a dataset of multiple trajectories.

        Returns
        -----------
        Trajectory
        """
        pa_table = pa_pq.read_table(file_name)
        if identifier:
            pa_table = pa_table.filter(
                pa.compute.field("identifier") == identifier,
                null_selection_behavior="drop",
            )
        config = pa_table.to_pydict()
        config["num_ionic_steps"] = len(config["elements"])
        for k in ("elements", "identifier"):
            config[k] = config[k][0]
        return cls(**config)

    def to_pmg(self, frame_props: Sequence[str] | None = None) -> PmgTrajectory:
        """
        Create a pymatgen Trajectory.

        Parameters
        -----------
        frame_props : Sequence of str or None (default)
            If not None, a list of model fields to populate the frame properties
            of the pymatgen Trajectory with.
            If None, defaults to all available fields.

        Returns
        -----------
        pymatgen.core.trajectory.Trajectory
        """
        frame_props = frame_props or [
            "energy",
            "e_wo_entrp",
            "e_fr_energy",
            "forces",
            "stress",
            "electronic_steps",
        ]

        species = [Element.from_Z(z) for z in self.elements]
        structures = []
        frame_properties = []

        for i, coords in enumerate(self.cart_coords):
            structure = Structure(
                lattice=self.constant_lattice
                if self.constant_lattice
                else self.lattice[i],  # type: ignore[index]
                species=species,
                coords=coords,
                coords_are_cartesian=True,
            )
            structures.append(structure)

            props = {}
            for k in frame_props:
                if (_prop := getattr(self, k, None)) is not None:
                    prop = _prop[i]
                    for cmth in ("model_dump", "tolist"):
                        if hasattr(prop, cmth):
                            prop = getattr(prop, cmth)()
                    props[k] = prop

            frame_properties.append(props)

        return PmgTrajectory.from_structures(
            structures,
            constant_lattice=self.constant_lattice is not None,
            frame_properties=frame_properties,
        )

    def to(
        self,
        file_name: str | Path | None = None,
        fmt: TrajFormat | str | None = None,
        **kwargs,
    ):
        """
        Generic interface to multiple trajectory formats.

        file_name : str, .Path, or None (default)
            If not None, the name of the file to write to.
            If fmt is None, the file format will be inferred from this.
        fmt : TrajFormat, str, or None (default)
            The format of the output trajectory. If file_name is None,
            and fmt is None, defaults to a parquet-compatible
            PyArrow table.
        **kwargs
            Any kwargs supported by Trajectory.to_* methods.
        """
        if file_name and not fmt:
            for _fmt in TrajFormat:
                if _fmt.value in str(file_name).lower():
                    fmt = _fmt
                    break
        elif not file_name and not fmt:
            fmt = TrajFormat.PARQUET

        if isinstance(fmt, str) and fmt.upper() in TrajFormat.__members__:
            fmt = TrajFormat[fmt.upper()]
        else:
            fmt = TrajFormat(fmt)

        if fmt in (TrajFormat.PMG, TrajFormat.ASE):
            traj = self.to_pmg(**kwargs)

            if fmt == TrajFormat.PMG:
                if file_name:
                    dumpfn(traj, file_name)
            elif fmt == TrajFormat.ASE:
                if hasattr(PmgTrajectory, "to_ase"):
                    traj = traj.to_ase(ase_traj_file=file_name)  # type: ignore[attr-defined]
                else:
                    raise ImportError(
                        "Ensure you have pymatgen>=2025.1.23 to use ASE trajectory interfaces."
                    )

        elif fmt == TrajFormat.PARQUET:
            traj = self.to_arrow(file_name=file_name)

        return traj
