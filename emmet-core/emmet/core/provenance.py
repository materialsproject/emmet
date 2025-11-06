"""Core definition of a Provenance Document"""

from __future__ import annotations

import json
import warnings
from typing import TYPE_CHECKING, Any, Annotated

from pybtex.database import BibliographyData, parse_string
from pybtex.errors import set_strict_mode
from pydantic import BaseModel, Field, BeforeValidator
from pymatgen.core import Lattice, Structure, PeriodicSite

from emmet.core.material_property import PropertyDoc
from emmet.core.math import Matrix3D
from emmet.core.symmetry import SymmetryData
from emmet.core.types.enums import ValueEnum
from emmet.core.types.pymatgen_types.structure_adapter import StructureType
from emmet.core.types.pymatgen_types.lattice_adapter import LatticeType
from emmet.core.types.typing import DateTimeType, IdentifierType

if TYPE_CHECKING:
    from typing_extensions import Self


class Database(ValueEnum):
    """
    Database identifiers for provenance IDs
    """

    ICSD = "icsd"
    Pauling_Files = "pf"
    COD = "cod"


class Author(BaseModel):
    """
    Author information
    """

    name: str | None = Field(None)
    email: str | None = Field(None)


def _remove_dupe_authors(authors: list[dict[str, Any] | Author]):
    """Remove duplicate authors from a list of Author objects or their dict rep."""
    _authors = [a.model_dump() if hasattr(a, "model_dump") else a for a in authors]
    authors_dict = {a["name"].lower(): a for a in _authors}
    return list(authors_dict.values())


def _migrate_legacy_history_data(
    config: list[dict[str, Any]] | list[History],
) -> list[History]:
    """Migrate legacy provenance and SNL `history` data as a classmethod.

    Parameters
    -----------
    config : list of history data as a dict or History object

    Returns
    -----------
    list of History objects.
    """

    top_level_history = [
        h.model_dump() if isinstance(h, History) else h for h in config
    ]
    history: list[History] = []
    for inp_hist in top_level_history:
        descs: list = []
        _flatten_nested_descriptions(descs, inp_hist.get("description"), 0)
        history.extend(
            [
                History(
                    **{k: inp_hist.get(k) for k in ("name", "url")},  # type: ignore[arg-type]
                    description=desc,
                )
                for desc in descs
            ]
        )
    return history


def _flatten_nested_descriptions(
    descs: list[ProvenanceDescription | None],
    entry: dict[str, Any] | None,
    depth: int,
    remark: str | None = None,
) -> None:
    """Flatten legacy provenance description data.

    Parameters
    -----------
    descs : list[ProvenanceDescription | None]
        Running list of provenance description data.
    entry : dict[str,Any] or None
        The current description
    depth : int
        Used to indicate how far recursively into the history
        this field is nested.
    remark : str or None (default)
        Optional remark to supersede that in entry.

    Returns
    -----------
    None : all data goes in to `descs`
    """

    if not entry:
        descs.append(None)
        return

    elif nested_hist := entry.pop("history", []):
        for sub_entry in nested_hist:
            _flatten_nested_descriptions(
                descs, sub_entry, depth + 1, remark=f"Nested history depth {depth}"
            )

    elif init_args := entry.get("init_args"):
        _flatten_nested_descriptions(
            descs, init_args, depth + 1, remark=f"init_args-depth-{depth}"
        )

    # always append current entry even if there were nested fields
    orig_remark = entry.pop("remark", None)
    if not remark:
        remark = orig_remark

    if entry.get("lattice"):
        entry["lattice"] = Lattice.from_dict(entry["lattice"])

    for k in ("sites", "input_structure"):
        if c := entry.get(k):
            try:
                if all(c.get(x) for x in ("sites", "lattice")):
                    entry[k] = Structure.from_sites(
                        [
                            PeriodicSite.from_dict(
                                site, lattice=Lattice.from_dict(c["lattice"])
                            )
                            for site in c["sites"]
                        ]
                    )
                else:
                    entry[k] = Structure.from_sites(
                        [
                            PeriodicSite.from_dict(site, lattice=entry.get("lattice"))
                            for site in c
                        ]
                    )
            except Exception:
                entry[k] = None

    if isinstance(entry.get("species_map"), list):
        # Some of these appear to be .items()
        entry["species_map"] = {v[0]: v[1] for v in entry["species_map"]}

    if isinstance(cif_data := entry.get("cif_data"), dict):
        # CIF fields from pymatgen are too heterogeneous to schematize.
        entry["cif_data"] = json.dumps(cif_data)

    descs.append(ProvenanceDescription(**entry, remark=remark))


class TransformationMeta(BaseModel):
    """Schema for transformation fields in history.description."""

    transformation_name: str | None = None
    formula: str | None = None
    structureid: int | None = None


class ProvenanceDescription(BaseModel):
    """Schema for heterogeneous provenance description data."""

    monty_class: str | None = Field(None, validation_alias="@class")
    monty_module: str | None = Field(None, validation_alias="@module")
    IZA_code: str | None = None
    algo: int | None = None
    cif_data: str | None = None
    crystal_id: int | None = None
    datetime: str | None = None
    description: str | None = None
    disordered_crystal_id: int | None = None
    experimental: bool = False
    fraction_to_remove: float | None = None
    fw_id: int | None = None
    icsd_id: int | None = None
    id: str | None = None
    input_structure: StructureType | None = None
    lattice: LatticeType | None = None
    materialsid: IdentifierType | None = None
    name: str | None = None
    original_file: str | None = None
    oxidation_states: dict[str, int] | None = None
    query: str | None = None
    remark: str | None = None
    scaling_matrix: Matrix3D | None = None
    sites: StructureType | None = None
    source: str | None = None
    spacegroup: SymmetryData | None = None
    specie_to_remove: str | None = None
    species_map: dict[str, str] | None = None
    species_to_remove: list[str] | None = None
    string: str | None = None
    structureid: int | None = None
    task_id: str | None = None
    task_type: str | None = None
    transformation_name: str | None = None
    transformations: list[TransformationMeta] | None = None
    version: str | None = None

    @classmethod
    def parse_str_or_dict(cls, x: str | dict[str, Any] | Self) -> Self:
        """Method used in validating string or dict-like input.

        Parameters
        -----------
        x : a string, dict, or ProvenanceDescription

        Returns
        -----------
        ProvenanceDescription
        """
        if isinstance(x, str):
            return cls(string=x)  # type: ignore[arg-type,call-arg]
        elif isinstance(x, dict):
            return cls(**x)
        return x


class History(BaseModel):
    """
    History of the material provenance
    """

    name: str
    url: str
    description: Annotated[
        ProvenanceDescription | None,
        BeforeValidator(ProvenanceDescription.parse_str_or_dict),
    ] = Field(None, description="Dictionary of extra data for this history node.")


HistoryType = Annotated[
    list[History] | None,
    BeforeValidator(_migrate_legacy_history_data),
]


class SNLAbout(BaseModel):
    """A data dictionary defining extra fields in a SNL"""

    references: str = Field(
        "", description="Bibtex reference strings for this material."
    )

    authors: list[Author] | None = Field(
        None, description="list of authors for this material."
    )

    remarks: list[str] | None = Field(
        None, description="list of remarks for the provenance of this material."
    )

    tags: list[str] | None = Field(None)

    database_IDs: dict[Database, list[str]] | None = Field(
        None, description="Database IDs corresponding to this material."
    )

    history: HistoryType = Field(
        None,
        description="list of history nodes specifying the transformations or orignation"
        " of this material for the entry closest matching the material input.",
    )

    created_at: DateTimeType = Field(description="The creation date for this SNL.")

    @classmethod
    def migrate_legacy_data(cls, config: dict[str, Any]) -> Self:
        """Migrate legacy SNL data with free-form JSON values to schematized."""
        config["history"] = _migrate_legacy_history_data(config.get("history", []))
        return cls(**config)


class SNLDict(BaseModel):
    """Pydantic validated dictionary for SNL"""

    about: SNLAbout

    snl_id: str = Field(..., description="The SNL ID for this entry")


class ProvenanceDoc(PropertyDoc):
    """
    A provenance property block
    """

    property_name: str = "provenance"

    created_at: DateTimeType = Field(
        description="creation date for the first structure corresponding to this material",
    )

    references: list[str] = Field(
        default_factory=list, description="Bibtex reference strings for this material"
    )

    authors: Annotated[
        list[Author],
        BeforeValidator(_remove_dupe_authors),
    ] = Field(default_factory=list, description="list of authors for this material")

    remarks: list[str] | None = Field(
        None, description="list of remarks for the provenance of this material"
    )

    tags: list[str] | None = Field(None)

    theoretical: bool = Field(
        True, description="If this material has any experimental provenance or not"
    )

    database_IDs: dict[Database, list[str]] | None = Field(
        None, description="Database IDs corresponding to this material"
    )

    history: HistoryType = Field(
        default_factory=list,
        description="list of history nodes specifying the transformations or orignation"
        " of this material for the entry closest matching the material input",
    )

    @classmethod
    def from_SNLs(
        cls,
        structure: Structure,
        snls: list[SNLDict],
        material_id: IdentifierType | None = None,
        **kwargs,
    ) -> "ProvenanceDoc":
        """
        Converts legacy Pymatgen SNLs into a single provenance document
        """

        assert (
            len(snls) > 0
        ), "Error must provide a non-zero list of SNLs to convert from SNLs"

        # Choose earliest created_at
        created_at = min([snl.about.created_at for snl in snls])
        # last_updated = max([snl.about.created_at for snl in snls])

        # Choose earliest history
        history = sorted(snls, key=lambda snl: snl.about.created_at)[0].about.history

        # Aggregate all references into one dict to remove duplicates
        refs = {}
        for snl in snls:
            try:
                set_strict_mode(False)
                entries = parse_string(snl.about.references, bib_format="bibtex")
                refs.update(entries.entries)
            except Exception as e:
                warnings.warn(
                    f"Failed parsing bibtex: {snl.about.references} due to {e}"
                )

        bib_data = BibliographyData(entries=refs)

        references = [ref.to_string("bibtex") for ref in bib_data.entries.values()]

        # TODO: Maybe we should combine this robocrystallographer?
        # TODO: Refine these tags / remarks
        remarks = list(set([remark for snl in snls for remark in snl.about.remarks]))  # type: ignore[union-attr]
        tags = [r for r in remarks if len(r) < 140]

        authors = [entry for snl in snls for entry in snl.about.authors]  # type: ignore[union-attr]

        # Check if this entry is experimental
        exp_vals = []
        for snl in snls:
            for entry in snl.about.history:  # type: ignore[union-attr]
                if entry.description is not None:
                    exp_vals.append(entry.description.experimental)

        experimental = any(exp_vals)

        # Aggregate all the database IDs
        snl_ids = {snl.snl_id for snl in snls}
        db_ids = {
            Database(db_id): [snl_id for snl_id in snl_ids if db_id in snl_id]
            for db_id in map(str, Database)  # type: ignore
        }

        # remove Nones and empty lists
        db_ids = {k: list(filter(None, v)) for k, v in db_ids.items()}
        db_ids = {k: v for k, v in db_ids.items() if len(v) > 0}

        fields = {
            "created_at": created_at,
            "references": references,
            "authors": authors,
            "remarks": remarks,
            "tags": tags,
            "database_IDs": db_ids,
            "theoretical": not experimental,
            "history": history,
        }

        return super().from_structure(
            material_id=material_id, meta_structure=structure, **fields, **kwargs
        )

    @classmethod
    def migrate_legacy_data(cls, config: dict[str, Any]) -> Self:
        """Migrate legacy provenance data with free-form JSON values to schematized."""
        config["history"] = _migrate_legacy_history_data(config.get("history", []))
        return cls(**config)
