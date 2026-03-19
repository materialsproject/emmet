"""Define basic schema for band theoretic properties."""

from __future__ import annotations

import numbers
from collections import defaultdict
from itertools import product
from typing import TYPE_CHECKING, Annotated

import numpy as np
from pydantic import BaseModel, BeforeValidator, Field, computed_field
from pymatgen.core import Lattice
from pymatgen.electronic_structure.bandstructure import (
    BandStructure as PmgBandStructure,
)
from pymatgen.electronic_structure.bandstructure import Kpoint
from pymatgen.electronic_structure.core import Orbital, Spin
from pymatgen.electronic_structure.dos import CompleteDos, Dos
from pymatgen.symmetry.bandstructure import HighSymmKpath

from emmet.core.electronic_structure import BSPathType
from emmet.core.math import Matrix3D, Vector3D
from emmet.core.settings import EmmetSettings
from emmet.core.types.pymatgen_types.structure_adapter import StructureType

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from typing import Any

    from pymatgen.core.sites import PeriodicSite
    from pymatgen.core.structure import Structure
    from typing_extensions import Self

BAND_GAP_TOL = 1e-4
SETTINGS = EmmetSettings()  # type: ignore[call-arg]


class BandTheoryBase(BaseModel):

    identifier: str | None = Field(None, description="The identifier of this object.")
    structure: StructureType | None = Field(
        None, description="The structure associated with this calculation."
    )

    def __str__(self) -> str:
        return (
            f"{self.__class__.__name__}({self.identifier or ''}"
            f"{': ' + self.structure.formula if self.structure else ''}"
        )

    def __repr__(self) -> str:
        return self.__str__()


def _deser_lattice(lattice: Lattice | dict | Matrix3D) -> Matrix3D:
    """Ensure the lattice matrix is stored only."""
    if isinstance(lattice, Lattice):
        return lattice.matrix
    elif isinstance(lattice, dict):
        return lattice.get("lattice")
    return lattice


class BandStructure(
    BandTheoryBase, populate_by_name=True, validate_by_alias=True, validate_by_name=True
):
    """Define the schema of band structures.

    This class is generic enough to accommodate both
    electronic and phonon band structures.
    """

    path_convention: BSPathType | None = Field(
        None, description="High symmetry path convention of the band structure"
    )

    kpath: list[str] | None = None

    labels_dict: dict[str, Vector3D] = Field(
        {}, description="The high-symmetry labels of specific q-points."
    )

    qpoints: list[Vector3D] = Field(
        description="The wave vectors (q-points) at which the band structure was sampled, in direct coordinates.",
    )

    reciprocal_lattice: Annotated[Matrix3D, BeforeValidator(_deser_lattice)] = Field(
        description="The reciprocal lattice.", validation_alias="lattice_rec"
    )

    def model_post_init(self, __context: Any) -> None:
        if self.structure and not self.path_convention:

            # Try the user-input labels if provided, as well as regenerating
            # them on the fly if path determination fails
            labels = [self.labels_dict, None] if self.labels_dict else [None]
            for label_set in labels:
                try:
                    self.path_convention, self.kpath, new_labels = next(
                        obtain_path_type(
                            self.structure,
                            self.qpoints,
                            user_kpoint_labels=label_set,
                        )
                    )
                    self.labels_dict = new_labels.copy()
                    if self.path_convention:
                        break
                except StopIteration:
                    pass


class ProjectedBS(BaseModel):
    """Light memory model for projected band structure data.

    Only C order is used.

    When the data is unraveled by numpy, you should get a 4-index
    tensor where:
        - Index 1: band index
        - Index 2: k-point index
        - Index 3: site index
        - Index 4: index for the orbital character, ordered as
            s, py, pz, px, dxy, dyz, dz2, dxz, dx2-y2,...
    """

    spin_up: list[float] | None = Field(
        None, description="The flattened spin-up band projections."
    )
    spin_down: list[float] | None = Field(
        None, description="The flattened spin-down band projections."
    )
    rank: tuple[int, int, int, int] = Field(
        description="The original shape of the band projections."
    )

    @classmethod
    def from_pmg_like(cls, projections: dict[Spin, np.ndarray]) -> Self:

        spins = list(projections)
        rank = projections[spins[0]].shape
        if not all(proj.shape == rank for proj in projections.values()):
            raise ValueError(
                "The band structure projections should have the same shape."
            )
        config = {
            f"spin_{spin.name}": proj.flatten(order="C")
            for spin, proj in projections.items()
        }
        return cls(
            **config,  # type: ignore[arg-type]
            rank=rank,  # type: ignore[arg-type]
        )

    def to_pmg_like(self) -> dict[Spin, np.ndarray]:
        return {
            spin: np.array(getattr(self, f"spin_{spin.name}")).reshape(
                self.rank, order="C"
            )
            for spin in Spin
            if getattr(self, f"spin_{spin.name}")
        }


class ElectronicBS(BandStructure):
    """Define an electronic band structure schema."""

    efermi: float = Field(
        description="The Fermi level (highest occupied energy level.)"
    )

    band_gap: float | None = Field(None, description="The value of the band gap.")

    spin_up_bands: list[list[float]] | None = Field(
        None,
        description="The eigen-energies of the spin-up electrons. The first index represents the band, the second the k-point index.",
    )

    spin_down_bands: list[list[float]] | None = Field(
        None,
        description="The eigen-energies of the spin-down electrons. The first index represents the band, the second the k-point index.",
    )

    is_direct: bool | None = Field(
        None, description="If the bandgap is non-zero, whether the band gap is direct."
    )

    projections: ProjectedBS | None = Field(
        None, description="The site- and spin-orbital-projected band structure."
    )

    @computed_field
    def is_metal(self) -> bool:
        """Whether the band gap is almost zero."""
        return (
            self.band_gap < BAND_GAP_TOL
            if isinstance(self.band_gap, numbers.Number)
            else False
        )

    @classmethod
    def from_pmg(cls, ebs: PmgBandStructure, **kwargs) -> Self:
        """Construct from a pymatgen band structure object."""
        band_gap_meta = ebs.get_band_gap()

        config = {
            "qpoints": [qpt.frac_coords for qpt in ebs.kpoints],
            "lattice_rec": ebs.lattice_rec.matrix,
            "efermi": ebs.efermi,
            "labels_dict": {
                label: qpt.frac_coords for label, qpt in (ebs.labels_dict or {}).items()
            },
            "structure": ebs.structure,
            "is_metal": ebs.is_metal(),
            "is_direct": band_gap_meta["direct"],
            "band_gap": band_gap_meta["energy"],
        }

        for spin in Spin:
            config[f"spin_{spin.name}_bands"] = ebs.bands.get(spin)
        config["projections"] = (
            ProjectedBS.from_pmg_like(ebs.projections)  # type: ignore[arg-type]
            if ebs.projections
            else None
        )
        return cls(**config, **kwargs)

    def to_pmg(self, pmg_cls: Callable = PmgBandStructure) -> PmgBandStructure:
        """Construct the pymatgen object from the current instance.

        Parameters
        -----------
        pmg_cls : PmgBandStructure or a subclass
            Because BandStructureSymmLine has the same constructor
            signature as PmgBandStructure, any PmgBandStructure-derived
            class which has the same signature can be used here.
        """
        rlatt = Lattice(self.reciprocal_lattice)

        bands = {}
        for spin in Spin:
            if v := getattr(self, f"spin_{spin.name}_bands", None):
                bands[spin] = np.array(v)

        return pmg_cls(
            [Kpoint(q, lattice=rlatt).frac_coords for q in self.qpoints],  # type: ignore[misc]
            bands,
            rlatt,
            self.efermi,
            labels_dict={
                k: Kpoint(v, lattice=rlatt).frac_coords  # type: ignore[misc]
                for k, v in (self.labels_dict or {}).items()
            },
            coords_are_cartesian=False,
            structure=self.structure,
            projections=self.projections.to_pmg_like() if self.projections else None,
        )


class ProjectedDos(BaseModel):
    """Atom and orbital projected DOS."""

    spin_up_densities: list[list[float] | None] | None = Field(
        None, description="The spin-up projected densities of state."
    )

    spin_down_densities: list[list[float] | None] | None = Field(
        None, description="The spin-down projected densities of state."
    )

    orbital: list[str | None] | None = Field(
        None, description="The orbital character of this DOS, if applicable."
    )

    site_index: list[int | None] | None = Field(
        None,
        description="The index of the atom in the structure onto which this DOS is projected.",
    )

    def _to_list_of_dict(self) -> list[dict[str, str | int | list[float]]]:
        """Possible serialization procedure."""
        return [
            {k: getattr(self, k)[i] for k in self.__class__.model_fields}
            for i in range(len(self.spin_up_densities or []))
        ]

    @classmethod
    def _from_list_of_dict(cls, lod: list[dict[str, str | int | list[float]]]) -> Self:
        """Possible deserialization route."""
        return cls(**{k: [entry.get(k) for entry in lod] for k in cls.model_fields})  # type: ignore[arg-type]

    @classmethod
    def from_pmg_like(
        cls,
        pdos: dict[PeriodicSite, dict[Orbital, dict[Spin, np.ndarray]]],
        structure: StructureType,
    ) -> Self:
        """Create a ProjectedDos from a pymatgen-like CompleteDos.pdos."""
        projs = [
            {
                **{
                    f"spin_{spin.name}_densities": sr_dos
                    for spin, sr_dos in spin_dos.items()
                },
                "orbital": orbital.name,
                "site_index": [
                    idx for idx, ref_site in enumerate(structure) if ref_site == site
                ][0],
            }
            for site, orb_spin_dos in pdos.items()
            for orbital, spin_dos in orb_spin_dos.items()
        ]

        return cls(
            **{  # type: ignore[arg-type]
                k: [proj.get(k) for proj in projs]
                for k in (
                    "spin_up_densities",
                    "spin_down_densities",
                    "orbital",
                    "site_index",
                )
            },
        )

    def to_pmg_like(
        self, structure: StructureType
    ) -> dict[PeriodicSite, dict[Orbital, dict[Spin, np.ndarray]]]:
        """Construct a pymatgen-like representation of the projected DOS."""
        pdos: defaultdict[
            PeriodicSite, defaultdict[Orbital, dict[Spin, np.ndarray]]
        ] = defaultdict(lambda: defaultdict(dict))
        for i, dens in enumerate(self.spin_up_densities or []):
            pdos[site := structure[self.site_index[i]]][  # type: ignore[index]
                orb := Orbital[self.orbital[i]]  # type: ignore[index,misc]
            ][Spin.up] = np.array(dens)
            if self.spin_down_densities and all(
                sdd for sdd in self.spin_down_densities
            ):
                pdos[site][orb][Spin.down] = np.array(self.spin_down_densities[i])

        return dict(pdos)


class ElectronicDos(BandTheoryBase):
    """Electronic density of states (DOS) with possible projections."""

    spin_up_densities: list[float] | None = Field(
        None, description="The spin-up densities of state."
    )

    spin_down_densities: list[float] | None = Field(
        None, description="The spin-down densities of state."
    )

    energies: list[float] | None = Field(
        None, description="The energies at which the DOS was calculated."
    )

    efermi: float | None = Field(None, description="The Fermi energy.")

    projected_densities: ProjectedDos | None = Field(
        None, description="The orbital- and site-projected DOS."
    )

    @property
    def _available_spins(self) -> list[Spin]:
        """Retrive spin indices of non-null spin data."""
        return [spin for spin in Spin if getattr(self, f"spin_{spin.name}_densities")]

    @classmethod
    def from_pmg(cls, dos: Dos | CompleteDos, **kwargs) -> Self:
        """Create an electronic DOS from a pymatgen object."""

        densities: dict[str, list[float]] = {
            f"spin_{spin.name}_densities": sr_dos.tolist()
            for spin, sr_dos in dos.densities.items()
        }

        pdos = (
            ProjectedDos.from_pmg_like(dos.pdos, dos.structure)  # type: ignore[arg-type]
            if isinstance(dos, CompleteDos)
            else None
        )

        return cls(
            **densities,  # type: ignore[arg-type]
            efermi=dos.efermi,
            energies=dos.energies.tolist(),
            structure=getattr(dos, "structure", None),
            projected_densities=pdos,
            **kwargs,
        )

    def to_pmg(self) -> Dos | CompleteDos:
        """Serialize to pymatgen."""
        if self.efermi is None:
            raise ValueError(
                "Fermi level unspecified, cannot create a pymatgen (Complete)Dos object."
            )

        densities: dict[Spin, np.ndarray] = {
            spin: np.array(getattr(self, f"spin_{spin.name}_densities"))
            for spin in self._available_spins
        }

        dos = Dos(self.efermi, np.array(self.energies), densities)
        if self.structure and self.projected_densities:
            return CompleteDos(
                self.structure,
                dos,
                self.projected_densities.to_pmg_like(self.structure),
            )
        return dos


def obtain_path_type(
    structure: Structure,
    kpoints: list[Vector3D],
    user_kpoint_labels: dict[str, Vector3D] | None = None,
    symprecs: list[float] = [SETTINGS.SYMPREC, 0.01],
    angtols: list[float] = [SETTINGS.ANGLE_TOL],
    atol: float = 1e-3,
    kpoint_tol: float = 1e-3,
) -> Generator:
    """Try to match a band structure path order to known path orders.

    Iterates over a list of `symprec` and `angle_tolerance` values to
    match paths to one of the path orders in `BSPathType` by checking
    that the kpoints list contains a reference k-point path dictated
    by the symmetry of the structure.

    Note that the k-points can be a superset of the high-symmetry path,
    the full path must be a sequential sublist of the input k-points.

    Ex: If the reference k-path is ["X","M","K","U"], a valid superset
    would be ["GAMMA", "X", "M", "K", "U", "X"], but an invalid superset
    would be ["X", "M", "GAMMA", "K", "U"] (as this breaks the reference order).

    The original k-point labels can be input by the user in `user_kpoint_labels`.
    This is often useful for older calculations because the high-symmetry
    k-points are not unique, and the path generated thereof will differ
    if the fractional coordinates of a given high-symmetry point represent
    a periodic image.

    Important notes:
    - pymatgen uses "\\Gamma" (BSPathType.setyawan_curtarolo),
        "GAMMA" (BSPathType.hinuma), and "Γ" (BSPathType.latimer_munro)
        to represent the Gamma point.
    - Sometimes legacy electronic structure data includes both
        the path set by a particular algorithm, plus a few extra
        points. We only check that the path matches up to the
        default high-symmetry path.

    Parameters
    -----------
    structure : pymatgen .Structure
        Structure associated with the bandstructure
    kpoints : list of tuple[float,float,float]
        A list of (all) k-points included in the bandstructure.
    symprecs : list[float] = [SETTINGS.SYMPREC,0.01]
        List of `symprec` values to pass to `HighSymmKpath`
    angtols : list[float] = [SETTINGS.ANGLE_TOL]
        List `angle_tolerance` values to pass to `HighSymmKpath`
    atol : float = 1e-5
        Absolute tolerance used by `HighSymmKpath`
    kpoint_tol : float = 1e-3
        Absolute tolerance for matching fractional k-point coordiantes

    Yields
    -----------
    BSPathType
    """
    for path_type in BSPathType:
        found_path_type = False
        for symprec, angtol in product(symprecs, angtols):
            if found_path_type:
                break

            try:
                hskp = HighSymmKpath(
                    structure,
                    has_magmoms=False,
                    magmom_axis=None,
                    path_type=path_type.value,
                    symprec=symprec,
                    angle_tolerance=angtol,
                    atol=atol,
                )

                kpoint_labels = user_kpoint_labels or {
                    k: tuple(v.tolist()) for k, v in hskp.kpath["kpoints"].items()
                }
                ref_path = [
                    kpt for kpt_group in hskp.kpath["path"] for kpt in kpt_group
                ]
                inferred_kpath = _get_kpath(kpoint_labels, kpoints)
                num_extra = len(inferred_kpath) - len(ref_path)
            except Exception:
                continue

            if (
                # check that the path orders are the same
                ref_path == inferred_kpath
                # or that the inferred path contains the reference one as a subset
                or (num_extra > 0 and _coarse_list_superset(inferred_kpath, ref_path))
            ):
                found_path_type = True
                yield path_type, inferred_kpath, kpoint_labels

    if not found_path_type:
        yield None, None, {}


def _coarse_list_superset(test: list, ref: list) -> bool:
    diff_len = len(test) - len(ref)
    if test[:diff_len] == ref or test[diff_len:] == ref:
        return True
    for i in range(1, diff_len):
        if test[i : len(ref) + i] == ref:
            return True
    return False


def _get_kpath(
    kpoints_labels: dict[str, Vector3D], kpoints: list[Vector3D]
) -> list[str]:
    labels = sorted(kpoints_labels)
    ref_kpoints = np.array([kpoints_labels[k] for k in labels])
    kpts = np.array(kpoints)
    norms = np.array([np.linalg.norm(kpt - ref_kpoints, axis=1) for kpt in kpts])
    ordered_labels = [labels[np.argmin(norm)] for norm in norms if norm.min() < 1e-5]
    processed_labels: list[str] = []
    for i, lbl in enumerate(ordered_labels):
        if i > 0 and lbl == processed_labels[-1]:
            continue
        processed_labels.append(lbl)
    return processed_labels
