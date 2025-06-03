"""Test base archival features."""

from pymatgen.core import Structure
import numpy as np

from emmet.archival.atoms import _RECIPROCAL, StructureArchive


def test_structure_archive(tmp_dir):
    structure = Structure(
        3.5 * np.array([[-0.5, 0.5, 0.5], [0.5, -0.5, 0.5], [0.5, 0.5, -0.5]]),
        [{"Na": 0.5, "K+": 0.5}, "Cl0.5-"],
        [[0.0, 0.0, 0.0], [0.5, 0.5, 0.5]],
    )
    structure.add_site_property(
        "selective_dynamics", [[True, True, False], [False, False, True]]
    )

    struct_archive = StructureArchive(structure=structure)

    # test round trip on structure --> pandas roundtrip
    columnar_struct = struct_archive.as_columnar()
    assert len(columnar_struct) == len(structure)
    assert np.all(
        np.abs(np.array(columnar_struct.attrs["lattice"]) - structure.lattice.matrix)
        < 1e-6
    )

    # Needs work? Should we do HDF5/zarr for structures?
    """
    # test roundtrip on structure --> hdf5 / zarr rountrip
    for fmt in ("h5","zarr"):
        archive = Path(f"structure.{fmt}")
        struct_archive.to_archive(archive)
        assert archive.exists() and os.path.getsize(archive) > 0.
        struct_copy = StructureArchive.extract(archive)
        assert struct_copy == structure
    """
    assert all(letter in columnar_struct.columns for letter in _RECIPROCAL)

    for k in ("atomic_num", "oxi_state", "occu"):
        assert len([c for c in columnar_struct.columns if c.startswith(k)]) == max(
            len(site.species) for site in structure
        )

    structure_copy = StructureArchive.columnar_to_structure(columnar_struct)
    assert structure == structure_copy

    structure.remove_oxidation_states()
    columnar_struct = StructureArchive.structure_to_columnar(structure)
    assert all("oxi_state" not in c for c in columnar_struct.columns)

    structure.replace_species({"K": "Na"})
    columnar_struct = StructureArchive.structure_to_columnar(structure)
    assert all("oxi_state" not in c for c in columnar_struct.columns)
