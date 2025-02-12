"""High-efficiency archival format for trajectories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import h5py
import numpy as np
import pandas as pd
import zarr

try:
    from ase.io.trajectory import TrajectoryReader as AseTrajReader
except ImportError:
    AseTrajReader = None  # type: ignore[misc]

from pymatgen.core import Structure
from pymatgen.core.trajectory import Trajectory as PmgTrajectory

from emmet.archival.base import Archiver, ArchivalFormat
from emmet.archival.utils import StrEnum

if TYPE_CHECKING:
    from typing import Any
    from typing_extensions import Self

    from emmet.core.tasks import TaskDoc


class TrajectoryProperty(StrEnum):
    structure = "structure"
    species = "species"
    lattice = "lattice"
    coordinates = "fractional_coordinates"
    energy = "energy"
    forces = "forces"
    stress = "stress"
    stress_voigt = "stress_voigt"
    magmom = "magmom"
    charge = "charge"


@dataclass
class TrajArchive(Archiver):
    """
    General-purpose class for storing constant-composition trajectories.

    Supports storing trajectories as JSONable dict, HDF5, zarr,
    pandas DataFrame, pymatgen Trajectory, and ASE trajectory.
    """

    lattice_match_tol: float = 1.0e-6
    all_lattices_equal: bool | None = None

    def __post_init__(self) -> None:
        """Ensure that structure information is included and parsed."""
        super().__post_init__()

        use_from_dict_rep = all(
            TrajectoryProperty(prop) in self.parsed_objects
            for prop in ("lattice", "species", "fractional_coordinates")
        )

        if (
            not use_from_dict_rep
            and TrajectoryProperty.structure not in self.parsed_objects
        ):
            raise ValueError(
                "You must specify a set of structures, or identically a set of lattices, species, and atomic coordinates!"
            )

        if use_from_dict_rep:
            self.num_sites = len(self.species)
            self.num_steps = len(self.fractional_coordinates)
        else:
            self.num_sites = len(self.structure[0])
            self.num_steps = len(self.structure)

        if self.all_lattices_equal is None:
            self.all_lattices_equal = all(
                np.all(
                    np.abs(
                        self.structure[i].lattice.matrix
                        - self.structure[j].lattice.matrix
                    )
                )
                < self.lattice_match_tol
                for i in range(self.num_steps)
                for j in range(i + 1, self.num_steps)
            )

        if self.parsed_objects.get(TrajectoryProperty.lattice) is None:
            if self.all_lattices_equal:
                self.parsed_objects[TrajectoryProperty.lattice] = np.array(
                    [self.structure[0].lattice.matrix]
                )
            else:
                self.parsed_objects[TrajectoryProperty.lattice] = np.array(
                    [structure.lattice.matrix for structure in self.structure]
                )

        if self.parsed_objects.get(TrajectoryProperty.coordinates) is None:
            self.parsed_objects[TrajectoryProperty.coordinates] = np.array(
                [
                    [site.frac_coords for site in structure]
                    for structure in self.structure
                ]
            )

        self._typing = {
            k: np.array(v).shape[1:] or (1,) for k, v in self.parsed_objects.items()
        }

    @classmethod
    def from_pymatgen_trajectory(
        cls, traj_file: str | Path | PmgTrajectory, **kwargs
    ) -> TrajArchive:
        """
        Instantite a TrajArchive from a pymatgen Trajectory.

        Parameters
        -----------
        traj_file : str, Path, or pymatgen.core.trajectory.Trajectory
            If a str or Path, the file path of the pymatgen-format trajectory.
            This class will store all site_properties and frame_properties of the
            Trajectory as `properties`.
        **kwargs
            kwargs of TrajArchive

        Returns
        ----------
        TrajArchive
        """

        traj: PmgTrajectory = (
            PmgTrajectory.from_file(traj_file)
            if isinstance(traj_file, (str, Path))
            else traj_file
        )

        properties = set()
        frame_properties = traj.frame_properties or [{} for _ in range(len(traj))]
        for idx in range(len(traj)):
            properties.update(set(frame_properties[idx] | traj[idx].site_properties))

        parsed_objects: dict[TrajectoryProperty | str, Any] = {
            k: [None for _ in range(len(traj))]
            for k in ["structure"] + list(properties)
        }

        for idx, structure in enumerate(traj):
            parsed_objects["structure"][idx] = structure
            for k, v in (traj[idx].site_properties | frame_properties[idx]).items():
                parsed_objects[k][idx] = v

        kwargs.update({"all_lattices_equal": traj.constant_lattice})

        return cls(parsed_objects, **kwargs)

    @classmethod
    def from_task_doc(
        cls,
        task_doc: TaskDoc,
        properties: list[TrajectoryProperty] | None = None,
        **kwargs,
    ) -> TrajArchive:
        """
        Instantite a TrajArchive from an emmet-core TaskDoc.

        Parameters
        -----------
        task_doc : emmet-core TaskDoc
            This class will pull all trajectory information from the `ionic_steps` field
            of each `calcs_reversed`, in the correct chronological order.
        properties : list of TrajectoryProperty
            An optional list of which known trajectory properties to pull from `ionic_steps`.
            If None, defaults to `structure` (required), `energy`, `forces`, and `stress`.
        **kwargs
            kwargs of TrajArchive

        Returns
        ----------
        TrajArchive
        """
        properties = properties or [
            TrajectoryProperty[k] for k in ("structure", "energy", "forces", "stress")
        ]
        translation = {"energy": "e_0_energy"}

        site_properties = set()
        for cr in task_doc.calcs_reversed[::-1]:
            for ionic_step in cr.output.ionic_steps:
                site_properties.update(set(ionic_step.structure.site_properties))

        parsed_objects: dict[TrajectoryProperty | str, Any] = {
            k: [] for k in properties + list(site_properties)
        }

        # un-reverse the calcs_reversed
        for cr in task_doc.calcs_reversed[::-1]:
            for ionic_step in cr.output.ionic_steps:
                for k in properties:
                    parsed_objects[k].append(getattr(ionic_step, translation.get(k, k)))
                for k in site_properties:
                    parsed_objects[k].append(
                        ionic_step.structure.site_properties.get(k)
                    )

        return cls(parsed_objects, **kwargs)

    @staticmethod
    def to_dict(
        archive: str | Path | h5py.Group | zarr.Group, group_key: str | None = None
    ) -> dict[str | TrajectoryProperty, Any]:
        """
        Convert either an archive on the file system or in memory to a dict.

        Parameters
        -----------
        archive : str or Path or h5py.Group or zarr.Group
            If a str or Path, the path to an existing hierarchical trajectory archive.
            If an h5py or zarr Group, the in-memory group to use.
        group_key : str or None (default)
            If a str, the hierarchical path to the trajectory.

        Returns
        -----------
        A low-memory JSONable dict representation of the trajectory.
        """

        archive_was_file = False
        ext = None
        if isinstance(archive, (str, Path)):
            archive_was_file = True
            ext = Path(archive).suffix.split(".")[-1]
            if ext == ArchivalFormat.HDF5:
                _loader = h5py.File
            elif ext == ArchivalFormat.ZARR:
                _loader = zarr.open

            archive = _loader(archive, "r")

        group = archive[group_key if group_key is not None else "/"]

        parsed_objects = {
            k: group.attrs[k]
            for k in (
                "species",
                "constant_lattice",
            )
        }
        if group.attrs["constant_lattice"]:
            parsed_objects[TrajectoryProperty.lattice] = group.attrs["lattice"]

        blocks = {}
        ranks = {}
        for icol, col in enumerate(group.attrs["columns"]):
            compound_idx = col.split("-")
            try:
                prop = TrajectoryProperty(compound_idx[0])
            except ValueError:
                try:
                    prop = TrajectoryProperty[compound_idx[0].split(".")[-1]]
                except ValueError:
                    prop = compound_idx[0]
            if prop not in blocks:
                blocks[prop] = [icol, -1]
                ranks[prop] = [-1 for _ in range(len(compound_idx[1:]))]
            blocks[prop][1] = max(blocks[prop][1], icol)
            for i, idx in enumerate(compound_idx[1:]):
                ranks[prop][i] = max(ranks[prop][i], int(idx) + 1)

        for prop, block in blocks.items():
            ncol = block[1] - block[0]
            if ncol == 0:
                # scalar properties
                parsed_objects[prop] = np.array(group["trajectory"][:, block[0]])
            else:
                parsed_objects[prop] = np.array(
                    [
                        np.array(row[block[0] : block[1] + 1]).reshape(
                            tuple(ranks[prop])
                        )
                        for row in group["trajectory"]
                    ]
                )

        if archive_was_file and ext == ArchivalFormat.HDF5:
            archive.close()

        return parsed_objects

    @staticmethod
    def order_sites(sites: list | Structure, site_order: list):
        running_sites = list(range(len(sites)))
        ordered_sites = []
        for ref_site in site_order:
            for idx in running_sites:
                if sites[idx].species == ref_site.species:
                    ordered_sites.append(sites[idx])
                    running_sites.remove(idx)
                    break

    def to_group(
        self, group: h5py.Group | zarr.Group, group_key: str | None = None
    ) -> None:
        """Append data to an existing HDF5-like file group."""

        if group_key is not None:
            group.create_group(group_key)
            group = group[group_key]

        df = self.to_dataframe()

        for k in (
            "num_sites",
            "num_steps",
            "constant_lattice",
            "species",
            "lattice",
        ):
            if (attr := df.attrs.get(k)) is not None:
                group.attrs[k] = attr

        group.attrs["columns"] = df.columns.to_list()
        group.create_dataset("trajectory", data=df.to_numpy(), **self.compression)

    def to_dataframe(self) -> pd.DataFrame:
        """Put trajectory in columnar DataFrame format."""

        species_order = [site.species_string for site in self.structure[0]]

        skip_props = {TrajectoryProperty.structure}
        if self.all_lattices_equal:
            skip_props.update({TrajectoryProperty.lattice})
        use_props = set(self.parsed_objects.keys()).difference(skip_props)

        columnar_data_rank = 0
        for prop in use_props:
            columnar_data_rank += np.prod(self._typing[prop]).astype(int)

        columns = []
        columnar_data = np.zeros((self.num_steps, columnar_data_rank))
        iprop = 0

        for prop in use_props:
            ncol = np.prod(self._typing[prop]).astype(int)
            prop_data = self.parsed_objects.get(prop)

            columnar_data[:, iprop : iprop + ncol] = [
                np.ravel(prop_data_step) for prop_data_step in prop_data
            ]
            unraveled_idx = np.unravel_index(list(range(ncol)), self._typing[prop])
            if len(unraveled_idx) == 1:
                columns += [f"{prop}-{idx}" for idx in range(ncol)]
            elif len(unraveled_idx) == 2:
                columns += [
                    f"{prop}-{unraveled_idx[0][idx]}-{unraveled_idx[1][idx]}"
                    for idx in range(ncol)
                ]
            iprop += ncol

        dataframe = pd.DataFrame(
            data=columnar_data,
            columns=columns,
            index=None,
        )

        dataframe.attrs = {
            "num_sites": self.num_sites,
            "num_steps": self.num_steps,
            "species": species_order,
            "constant_lattice": self.all_lattices_equal,
        }

        if self.all_lattices_equal:
            dataframe.attrs["lattice"] = self.structure[0].lattice.matrix.tolist()

        return dataframe

    @classmethod
    def from_archive(cls, archive_path: str | Path, **kwargs) -> Self:
        data = cls.to_dict(archive_path)
        constant_lattice = data.pop("constant_lattice")
        return cls(parsed_objects=data, all_lattices_equal=constant_lattice, **kwargs)

    @classmethod
    def to_pymatgen_trajectory(
        cls, file_name: str | Path, group_key: str | None = None
    ) -> PmgTrajectory:
        """Create a pymatgen Trajectory from an archive.

        Parameters
        -----------
        file_name : str or Path
            Name of the archive to transform to a pymatgen Trajectory.
        group_key : str or None (default)
            If a str, the name of the hierarchical group within an HDF5/zarr
            archive where the trajectory is located.

        Returns
        ----------
        pymatgen.core.trajectory.Trajectory object.
        """

        data: dict[str | TrajectoryProperty, Any] = cls.to_dict(
            file_name, group_key=group_key
        )
        num_steps = len(data["fractional_coordinates"])
        if data["constant_lattice"]:
            structures = [
                Structure(
                    data["lattice"], data["species"], coords, coords_are_cartesian=False
                )
                for coords in data["fractional_coordinates"]
            ]
        else:
            structures = [
                Structure(
                    data["lattice"][idx],
                    data["species"],
                    coords,
                    coords_are_cartesian=False,
                )
                for idx, coords in enumerate(data["fractional_coordinates"])
            ]

        frame_properties = [
            {
                k.value: data[k][idx]
                for k in TrajectoryProperty
                if k in data
                and k not in ("lattice", "fractional_coordinates", "structure")
            }
            for idx in range(num_steps)
        ]

        return PmgTrajectory.from_structures(
            structures,
            constant_lattice=data["constant_lattice"],
            frame_properties=frame_properties,
        )

    @classmethod
    def to_ase_trajectory(
        cls,
        file_name: str | Path,
        ase_traj_file: str | Path | None = None,
        group_key: str | None = None,
    ) -> AseTrajReader:
        """
        Create an ASE Trajectory from an archive.

        Parameters
        -----------
        file_name : str or Path
            Name of the archive to transform to an ASE Trajectory.
        ase_traj_file : str, Path, or None (default)
            If not None, the name of the file to write the ASE trajectory to.
        group_key : str or None (default)
            If a str, the name of the hierarchical group within an HDF5/zarr
            archive where the trajectory is located.

        Returns
        ----------
        ase.io.Trajectory object.
        """

        if AseTrajReader is None:
            raise ImportError(
                "You must install ASE to use the ASE trajectory functionality of this class."
            )

        from tempfile import NamedTemporaryFile
        from ase import Atoms
        from ase.calculators.singlepoint import SinglePointCalculator
        from ase.io import Trajectory as AseTrajectory

        ase_traj_file = ase_traj_file or NamedTemporaryFile().name

        data = cls.to_dict(file_name, group_key=group_key)

        for idx, coords in enumerate(data["fractional_coordinates"]):
            atoms = Atoms(symbols=data["species"], positions=coords, pbc=True)
            atoms.calc = SinglePointCalculator(
                atoms=atoms,
                **{
                    k: data[k][idx]
                    for k in (
                        "energy",
                        "forces",
                        "stress",
                        "magmom",
                    )
                    if k in data
                },
            )
            with AseTrajectory(
                ase_traj_file, "a" if idx > 0 else "w", atoms=atoms
            ) as _traj_file:
                _traj_file.write()

        return AseTrajectory(ase_traj_file, "r")
