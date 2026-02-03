"""Define schemas for trajectories."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from monty.dev import requires
from monty.serialization import dumpfn
from pydantic import BaseModel, Field, model_validator
from pymatgen.core import Element, Molecule, Structure
from pymatgen.core.trajectory import Trajectory as PmgTrajectory

from emmet.core.math import Vector3D, Matrix3D
from emmet.core.types.enums import ValueEnum
from emmet.core.vasp.models import ElectronicStep
from emmet.core.vasp.calc_types import RunType, TaskType

logger = logging.getLogger(__name__)

try:
    import pyarrow as pa
    import pyarrow.parquet as pa_pq
    from pyarrow import Table as ArrowTable

except ImportError:
    pa = None
    pa_pq = None
    ArrowTable = None

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any

    from typing_extensions import Self

    from pymatgen.io.vasp import Vasprun


class TrajFormat(ValueEnum):
    """Define known trajectory formats."""

    PMG = "json"
    ASE = "traj"
    PARQUET = "parquet"


class _MDMixin(BaseModel):
    """Mix-in for molecular dynamics runs."""

    magmoms: list[list[float]] | None = Field(
        None, description="The magnetic moments at each ionic step."
    )

    temperature: list[float] | None = Field(
        None, description="The temperature at each ionic step."
    )

    velocities: list[list[Vector3D]] | None = Field(
        None, description="The velocities of each atom."
    )

    time_step: float | None = Field(
        None, description="The time step used in the calculation."
    )

    ionic_step_properties: set[str] = Field(
        {"magmoms", "temperature", "velocities", "time_step"},
        exclude=True,
        description="The properties included at each ionic step.",
    )

    @model_validator(mode="after")
    def add_props(self) -> Self:
        self.ionic_step_properties = self.ionic_step_properties.union(
            {"magmoms", "temperature", "velocities"}
        )
        return self


def _order_z_list(new_z: list[int], ref_z: list[int]) -> tuple[list[int], bool]:
    """Order a list of proton numbers (Z) according to a reference list.

    Parameters
    -----------
    new_z : list of int
        List of new proton numbers to order
    ref_z : list of in
        List of reference proton numbers

    Returns
    -----------
    list of int
        New site indices with matching order
    bool
        Whether the order changed
    """
    running_sites = list(range(len(new_z)))
    if new_z == ref_z:
        return running_sites, False

    reordered_index = []
    for z in ref_z:
        for idx in running_sites:
            if new_z[idx] == z:
                reordered_index.append(idx)
                running_sites.remove(idx)
                break

    if len(running_sites) > 0:
        raise ValueError("Cannot order atoms according to reference Z list.")
    return reordered_index, True


class AtomRelaxTrajectory(BaseModel):
    """Atomistic only, low-memory schema for relaxation trajectories that can interface with parquet, pymatgen, and ASE."""

    elements: list[int] = Field(
        description="The proton number Z of the elements in the sites"
    )

    cart_coords: list[list[Vector3D] | None] = Field(
        description="The Cartesian coordinates (Å) of the sites at each ionic step"
    )
    num_ionic_steps: int = Field(description="The number of ionic steps.")

    lattice: list[Matrix3D] | None = Field(
        None,
        description=(
            "If a list containing only one 3x3 matrix, it is assumed that "
            "the lattice was held constant through the simulation. "
            "If a list of (multiple) 3x3 matrices, this should be the lattice "
            "at each ionic step in the calculation. "
            "If None, a non-periodic system is assumed."
        ),
    )

    energy: list[float] | None = Field(
        None, description="The total energy at each ionic step."
    )

    forces: list[list[Vector3D]] | None = Field(
        None, description="The interatomic forces."
    )
    stress: list[Matrix3D] | None = Field(None, description="The 3x3 stress tensor.")

    ionic_step_properties: set[str] = Field(
        {
            "energy",
            "forces",
            "stress",
        },
        exclude=True,
        description="The properties included at each ionic step.",
    )

    @model_validator(mode="before")
    def reset_num_ionic_steps(cls, config: Any) -> Any:
        config["num_ionic_steps"] = len(config["cart_coords"])
        config["elements"] = [
            Element(ele).Z if isinstance(ele, str) else int(ele)
            for ele in config["elements"]
        ]
        return config

    @property
    def ionic_step_properties_used(self) -> set[str]:
        """Return list of populated fields."""
        used_fields = {
            k for k in self.ionic_step_properties if getattr(self, k, None) is not None
        }

        # Because `self.lattice == 1` can indicate a frozen lattice if `self.num_ionic_steps > 1`
        # and a static calculation otherwise, check here that the lattice is a property
        # that varies with frames
        if isinstance(self.lattice, list) and len(self.lattice) == self.num_ionic_steps:
            used_fields.add("lattice")
        return used_fields

    def __repr__(self) -> str:
        """Print summary data."""
        return (
            f"{self.__class__.__module__}.{self.__class__.__name__} "
            f"({self.num_ionic_steps} ionic steps) with data: "
            f"{', '.join(sorted(self.ionic_step_properties_used))}."
        )

    def __hash__(self) -> int:
        """Used to verify roundtrip conversion of Trajectory."""
        return hash(self.model_dump_json())

    def __len__(self) -> int:
        """Get number of ionic steps."""
        return self.num_ionic_steps

    def __getitem__(self, index: int | slice) -> AtomRelaxTrajectory:
        if isinstance(index, int):
            if index < 0:
                index = len(self) + index
        _slice: slice = slice(index, index + 1) if isinstance(index, int) else index

        config = {}
        all_ionic_step_props = self.ionic_step_properties.union(
            {
                "lattice",
                "cart_coords",
            }
        )
        for k in self.__class__.model_fields:
            v = getattr(self, k)
            if v and k in all_ionic_step_props:
                config[k] = v[_slice]
            elif v:
                config[k] = v
        return type(self)(**config)

    @staticmethod
    def reorder_sites(
        structure: Structure | Molecule, ref_z: list[int]
    ) -> tuple[Structure | Molecule, list[int], bool]:
        """
        Ensure that the sites in a structure match the order in a set of reference Z values.

        Quick returns if the structure already matches the reference order.

        Parameters
        -----------
        structure : pymatgen .Structure or .Molecule
            Structure or Molecule to order sites in
        ref_z : list of int
            List of proton numbers / Z values in the reference structure.

        Returns
        -----------
        pymatgen .Structure or .Molecule : structure matching the reference order of sites
        list of int : indices in the original structure which are reordered
        bool : Whether the order changed
        """

        reordered_index, order_changed = _order_z_list(
            [site.species.elements[0].Z for site in structure], ref_z
        )

        if not order_changed:
            return structure, reordered_index, order_changed

        pmg_cls = Structure if isinstance(structure, Structure) else Molecule
        return (
            pmg_cls.from_sites([structure.sites[idx] for idx in reordered_index]),
            reordered_index,
            order_changed,
        )

    @classmethod
    def _from_dict(
        cls,
        props: dict[str, Any],
        constant_lattice: bool = False,
        lattice_match_tol: float | None = None,
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
        is_structure = isinstance(structures[0], Structure)
        if is_structure and any(not structure.is_ordered for structure in structures):
            raise ValueError(
                "At this time, the Trajectory model in emmet does not support disordered structures."
            )

        num_ionic_steps = len(structures)

        props["elements"] = [site.species.elements[0].Z for site in structures[0]]
        if (
            is_structure
            and constant_lattice
            or (
                lattice_match_tol
                and all(
                    np.all(
                        np.abs(
                            structures[i].lattice.matrix - structures[j].lattice.matrix
                        )
                        < lattice_match_tol
                    )
                    for i in range(num_ionic_steps)
                    for j in range(i + 1, num_ionic_steps)
                )
            )
        ):
            props["lattice"] = [structures[0].lattice.matrix]
        elif is_structure:
            props["lattice"] = [structure.lattice.matrix for structure in structures]

        reordered: list[tuple[Structure | Molecule, list[int], bool]] = [
            cls.reorder_sites(structure, props["elements"]) for structure in structures
        ]

        # Ensure that coordinates and properties associated with sites have consistent ordering
        props["cart_coords"] = [entry[0].cart_coords for entry in reordered]

        if any(entry[2] for entry in reordered):
            for site_prop_key in {"magmoms", "forces"}:
                if (site_prop_val := props.pop(site_prop_key, None)) or (
                    site_prop_val := kwargs.pop(site_prop_key, None)
                ):
                    props[site_prop_key] = [
                        (
                            [site_prop_val[ion_step_idx][idx] for idx in entry[1]]
                            if entry[2]
                            else site_prop_key[ion_step_idx]
                        )
                        for ion_step_idx, entry in enumerate(reordered)
                    ]

        if len(esteps := props.get("electronic_steps", [])) > 0:
            props["num_electronic_steps"] = [len(estep) for estep in esteps]

        return cls(**props, **kwargs)

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
        self,
        file_name: str | Path | None = None,
        **write_file_kwargs,
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
            k: pa.array([v])
            for k, v in self.model_dump(mode="json").items()
            if hasattr(v, "__len__")
        }

        pa_table = pa.table(pa_config)
        if file_name:
            pa_pq.write_table(pa_table, file_name, **write_file_kwargs)

        return pa_table

    @classmethod
    def from_arrow(cls, pa_table: ArrowTable, identifier: str | None = None) -> Self:
        """
        Create a trajectory from an arrow Table.

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
        if identifier:
            pa_table = pa_table.filter(
                pa.compute.field("identifier") == identifier,
                null_selection_behavior="drop",
            )

        config = {
            k: pa_table[k].to_pylist()[0]
            for k in pa_table.column_names
            if k in cls.model_fields
        }
        return cls(**config)

    @classmethod
    def from_parquet(cls, file_name: str | Path, identifier: str | None = None) -> Self:
        """Create a Trajectory from a parquet file.

        Parameters
        -----------
        file_name : str | Path
            Path to the parquet file. Can be a remote path, e.g. AWS.
        identifier : str | None = None
            The string identifier for the task.
        """
        kwargs = {}
        if identifier:
            kwargs["filters"] = [("identifier", "=", identifier)]
        return cls.from_arrow(pa_pq.read_table(file_name, **kwargs))

    def to_pmg(
        self,
        frame_props: Iterable[str] | None = None,
        indices: int | slice | Iterable[int] | None = None,
    ) -> PmgTrajectory:
        """
        Create a pymatgen Trajectory.

        Parameters
        -----------
        frame_props : Sequence of str or None (default)
            If not None, a list of model fields to populate the frame properties
            of the pymatgen Trajectory with.
            If None, defaults to all available fields.
            If an empty iterable, no frame properties will be returned.
        indices : int, slice, iterable of int, or None
            If None (default), returns all frames
            If an int, the index of the frame to return
            If a slice, returns that range of frames
            If an iterable of int, returns those specific frames

            Frames are always returned in sequential order,
            even if the user-supplied indices are unsorted.

        Returns
        -----------
        pymatgen.core.trajectory.Trajectory
        """

        if frame_props is not None:
            frame_prop_keys: set[str] = set(frame_props).intersection(
                self.ionic_step_properties
            )
        else:
            frame_prop_keys = self.ionic_step_properties

        if "magmoms" in frame_prop_keys:
            frame_prop_keys.discard("magmoms")

        if indices:
            if isinstance(indices, slice):
                indices = set(range(indices.start, indices.stop, indices.step or 1))
            elif isinstance(indices, int):
                indices = {indices}
        else:
            indices = set(range(len(self)))

        species = [Element.from_Z(z) for z in self.elements]
        structures = []
        frame_properties = []

        for i in sorted({i for i in indices if self.cart_coords[i]}):
            site_properties = {}
            if magmoms := getattr(self, "magmoms", None):
                site_properties["magmoms"] = magmoms[i]

            if self.lattice:
                structure: Structure | Molecule = Structure(
                    lattice=(
                        self.lattice[0]
                        if len(self.lattice) == 1
                        else self.lattice[i]  # type: ignore[index]
                    ),
                    species=species,
                    coords=self.cart_coords[i],  # type: ignore[arg-type]
                    coords_are_cartesian=True,
                    site_properties=site_properties,
                )
            else:
                structure = Molecule(
                    species=species,
                    coords=self.cart_coords[i],  # type: ignore[arg-type]
                    site_properties=site_properties,
                )
            structures.append(structure)

            props = {}
            for k in frame_prop_keys:
                if _prop := getattr(self, k, []):
                    prop = _prop[i]
                    for cmth in ("model_dump", "tolist"):
                        if hasattr(prop, cmth):
                            prop = getattr(prop, cmth)()
                    props[k] = prop

            frame_properties.append(props)

        if self.lattice:
            return PmgTrajectory.from_structures(
                structures,  # type: ignore[arg-type]
                constant_lattice=len(self.lattice) == 1,
                frame_properties=frame_properties,
            )
        return PmgTrajectory.from_molecules(
            structures,  # type: ignore[arg-type]
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
            for _fmt in TrajFormat:  # type: ignore[attr-defined]
                if _fmt.value in str(file_name).lower():
                    fmt = _fmt
                    break
        elif not file_name and not fmt:
            fmt = TrajFormat.PARQUET

        if isinstance(fmt, str) and fmt.upper() in TrajFormat.__members__:
            fmt = TrajFormat[fmt.upper()]  # type: ignore[misc]
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


class AtomTrajectory(AtomRelaxTrajectory, _MDMixin):
    """Atomistic trajectory with extra keys for molecular dynamics runs."""


class RelaxTrajectory(AtomRelaxTrajectory):
    """Low memory schema for relaxation trajectories that can interface with parquet, pymatgen, and ASE.

    This schema is intended primarily for VASP relaxation trajectories, but could be adapted to
    generic electronic structure trajectories.

    Note that for VASP calculations, energies are in eV, forces in eV/Å, and stress tensors in kilobar.
    """

    electronic_steps: list[list[ElectronicStep]] | None = Field(
        None, description="The electronic steps within a given ionic step."
    )
    num_electronic_steps: list[int] | None = Field(
        None, description="The number of electronic steps within each ionic step."
    )

    e_wo_entrp: list[float] | None = Field(
        None,
        description="The total energy in eV without electronic pseudoentropy from smearing of the Fermi surface.",
    )
    e_fr_energy: list[float] | None = Field(
        None, description="The total electronic free energy in eV."
    )

    identifier: str | None = Field(
        None, description="Identifier of this trajectory, e.g., task ID."
    )

    task_type: TaskType | None = Field(
        None,
        description="The TaskType of the calculation used to generate this trajectory.",
    )

    run_type: RunType | None = Field(
        None,
        description="The RunType of the calculation used to generate this trajectory.",
    )

    ionic_step_properties: set[str] = Field(
        {
            "energy",
            "forces",
            "stress",
            "e_wo_entrp",
            "e_fr_energy",
            "electronic_steps",
        },
        description="The properties included at each ionic step.",
        exclude=True,
    )

    @property
    def has_full_output(self) -> bool:
        """Return true if a trajectory has all structures and SCF convergence info available."""
        return all(coord_set is not None for coord_set in self.cart_coords) and all(
            conv_list is not None for conv_list in self.convergence_data.values()
        )

    @property
    def convergence_data(self) -> dict[str, list[float] | None]:
        """Get convergence of energy and interatomic forces.

        If possible, energy convergence is taken at every electronic step.
        If not, it is taken at each ionic step (the final electronic step).

        Forces are taken at each ionic step.
        """
        conv_data: dict[str, list[float] | None] = {}

        if self.electronic_steps is None:
            ionic_step_keys = ["energy", "e_fr_energy", "e_wo_entrp", "forces"]
        else:
            ionic_step_keys = ["forces"]
            flattened_e_steps = []
            for e_step in self.electronic_steps:
                flattened_e_steps.extend(e_step)

            for k, remap in {
                "e_0_energy": "energy",
                "e_fr_energy": "e_fr_energy",
                "e_wo_entrp": "e_wo_entrp",
            }.items():
                list_data = [getattr(e_step, k, None) for e_step in flattened_e_steps]
                if not all(list_data):
                    ionic_step_keys.append(remap)
                    continue

                data = np.array(list_data)
                conv_data[remap] = np.abs(data[-1] - data).tolist()

        for k in ionic_step_keys:
            if (list_data := getattr(self, k)) is None:
                conv_data[k] = None
                continue

            if k == "forces":
                list_data = [np.linalg.norm(f) for f in list_data]

            data = np.array(list_data)
            conv_data[k] = np.abs(data[-1] - data).tolist()

        return conv_data

    @classmethod
    def from_vasprun(
        cls, vasprun: Vasprun, store_electronic_steps: bool = True, **kwargs
    ) -> Self:
        """Create a Trajectory from a VASP vasprun.xml.

        Parameters
        -----------
        vasprun : pymatgen Vasprun object
        store_electronic_steps : bool = True (default)
            Whether to store the electronic step information
        **kwargs : kwargs to pass to _from_dict / the document model
        """

        ionic_step_data = {
            "structure",
            "e_fr_energy",
            "e_wo_entrp",
            "e_0_energy",
            "forces",
            "stress",
        }
        remap = {"e_0_energy": "energy"}
        if store_electronic_steps:
            ionic_step_data.add("electronic_steps")

        if (
            vasprun.parameters.get("IBRION", -1) == 0
            and "time_step" in cls.model_fields
            and not kwargs.get("time_step")
        ):
            kwargs["time_step"] = vasprun.parameters.get("POTIM")

        istep_attr = "md_data" if vasprun.incar.get("ML_LMLFF") else "ionic_steps"
        return cls._from_dict(
            {
                remap.get(k, k): [
                    ionic_step.get(k) for ionic_step in getattr(vasprun, istep_attr, [])
                ]
                for k in ionic_step_data
            },
            **kwargs,
        )

    @requires(
        pa is not None, message="pyarrow must be installed to de-/serialize to parquet"
    )
    def to_arrow(
        self,
        file_name: str | Path | None = None,
        store_conv_data: bool = True,
        **write_file_kwargs,
    ) -> ArrowTable:
        """
        Create a PyArrow Table from a Trajectory.

        Parameters
        -----------
        file_name : str, .Path, or None (default)
            If not None, a file to write the parquet-format output to.
            Accepts any compression extension used by pyarrow.write_table
        store_conv_data : bool = True (default)
            Whether to store the data in `Trajectory.convergence_data`.
            Defaults to True to ensure that MP website convergence data is
            stored and easily accesible via parquet.
        **write_file_kwargs
            If file_name is not None, any kwargs to pass to
            pyarrow.parquet.write_file

        Returns
        -----------
        pyarrow.Table
        """
        pa_config = {
            k: pa.array([v])
            for k, v in self.model_dump(mode="json").items()
            if hasattr(v, "__len__")
        }

        for k in (
            "run_type",
            "task_type",
        ):
            if val := getattr(self, k):
                pa_config[k] = pa.array([val.value])

        if store_conv_data:
            for k, v in self.convergence_data.items():
                pa_config[f"{k}_convergence"] = pa.array([v])

        pa_config["has_full_output"] = [self.has_full_output]

        pa_table = pa.table(pa_config)
        if file_name:
            pa_pq.write_table(pa_table, file_name, **write_file_kwargs)

        return pa_table


class Trajectory(RelaxTrajectory, _MDMixin):
    """Trajectory with flexibility for electronic structure molecular dynamics."""
