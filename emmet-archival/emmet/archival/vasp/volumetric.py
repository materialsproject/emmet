from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.compute as pa_co
from pydantic import Field

from emmet.core.band_theory import ElectronicBS, ElectronicDos
from emmet.core.vasp.utils import VASP_VOLUMETRIC_FILES

from emmet.archival.base import Archiver
from emmet.archival.volumetric import VolumetricArchive
from emmet.archival.utils import zpath
from emmet.archival.vasp import PMG_OBJ

if TYPE_CHECKING:

    from collections.abc import Sequence
    from typing_extensions import Self

    from pymatgen.electronic_structure.bandstructure import BandStructure
    from pymatgen.electronic_structure.dos import CompleteDos, Dos
    from pymatgen.io.common import VolumetricData as PmgVolumetricData
    from pymatgen.io.vasp import Vasprun


class DosArchive(Archiver):
    """Archive/extract an electronic density of states (DOS)."""

    dos: ElectronicDos = Field(
        description="The DOS, possibly including structure and site-projections."
    )

    def to_arrow(self) -> pa.Table:
        """Convert DOS archive to arrow table."""
        return self.dos.to_arrow()

    @classmethod
    def from_arrow(cls, table: pa.Table) -> Dos | CompleteDos:
        """Extract a pymatgen DOS from an arrow table."""
        return ElectronicDos.from_arrow(table).to_pmg()

    @classmethod
    def from_vasprun(cls, vasprun: Vasprun) -> Self:
        """Create a DOS archive from a vasprun object."""
        return cls(dos=ElectronicDos.from_pmg(vasprun.complete_dos))


class BandStructureArchive(Archiver):
    """Archive/extract an electronic bandstructure."""

    band_structure: ElectronicBS = Field(description="The electronic band structure.")

    def to_arrow(self) -> pa.Table:
        return self.band_structure.to_arrow()

    @classmethod
    def from_arrow(cls, table: pa.Table) -> BandStructure:
        return ElectronicBS.from_arrow(table).to_pmg()


class VaspVolumetricArchive(Archiver):
    """Archive all CHGCAR-like volumetric data associated with a VASP calculation."""

    file_names: list[str] = Field(
        description="The names of the volumetric files included in the archive."
    )
    volumetric_archives: list[VolumetricArchive] = Field(
        description="Individual volumetric archives for the files in file_names."
    )
    identifier: str | None = Field(
        None, description="The identifier associated with this set of volumetric data."
    )

    @classmethod
    def from_directory(cls, dir_name: str | Path, **kwargs) -> VaspVolumetricArchive:
        calc_dir = Path(dir_name).resolve()
        file_names: list[str] = []
        vol_archs = []
        for file_name in set(VASP_VOLUMETRIC_FILES).intersection(PMG_OBJ):
            file_path = zpath(calc_dir / file_name)
            if file_path.exists():
                file_names.append(file_name)
                vol_data = PMG_OBJ[file_name].from_file(file_path)
                vol_archs.append(VolumetricArchive.from_pmg(vol_data))

        return cls(file_names=file_names, volumetric_archives=vol_archs)

    def to_arrow(self) -> pa.Table:
        """Create an arrow table of voumetric data."""

        # to ensure that the pyarrow schema contains augmentation data,
        # use either CHGCAR or POT first
        got_aug_data = False
        for schema_k in ("CHGCAR", "POT"):
            for schema_idx, fname in enumerate(self.file_names):
                if schema_k == fname:
                    got_aug_data = True
                    break
            if got_aug_data:
                break

        if not got_aug_data:
            schema_idx = 0

        tables = []
        for idx in [schema_idx] + [
            i for i in range(len(self.file_names)) if i != schema_idx
        ]:
            table = self.volumetric_archives[idx].to_arrow()
            table = table.append_column("file_name", pa.array([self.file_names[idx]]))
            table = table.append_column("identifier", pa.array([self.identifier]))
            tables.append(table)

        return pa.concat_tables(tables, promote_options="permissive")

    @classmethod
    def from_arrow(
        cls, table: pa.Table, file_names: Sequence[str] | None = None
    ) -> list[dict[str, PmgVolumetricData | str]]:
        """Extract volumetric data from an arrow table.

        Defaults to extracting all available data within an archive.
        """
        all_file_names = table["file_name"].to_pylist()[0]
        files = set(file_names or all_file_names).intersection(all_file_names)

        output_data: list[dict[str, PmgVolumetricData | str]] = []
        for identifier in set(table["identifier"].to_pylist()):
            if identifier is None:
                id_filter = ~pa_co.field("identifier").is_valid()
            else:
                id_filter = pa_co.field("identifier") == identifier

            for file_name in files:
                output_data.append(
                    {
                        "identifier": identifier,
                        "file_name": file_name,
                        "data": VolumetricArchive.from_arrow(
                            table.filter(
                                id_filter & (pa_co.field("file_name") == file_name)
                            )
                        ),
                    }
                )

        return output_data
