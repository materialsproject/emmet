"""Test phonon document models."""

from copy import deepcopy
from tempfile import NamedTemporaryFile

import numpy as np
import pytest
from monty.serialization import loadfn
from pymatgen.core import Structure
from pymatgen.phonon.dos import CompletePhononDos, PhononDos as PmgPhononDos

from emmet.core import ARROW_COMPATIBLE
from emmet.core.phonon import PhononBSDOSDoc, PhononDOS
from emmet.core.testing_utils import assert_schemas_equal

if ARROW_COMPATIBLE:
    import pyarrow as pa

    from emmet.core.arrow import arrowize


@pytest.fixture(scope="module")
def legacy_ph_task(test_dir):
    return loadfn(test_dir / "mp-23302_phonon.json.gz", cls=None)


def test_legacy_migration(legacy_ph_task):
    # ensure that legacy phonon data can be migrated to current schema

    assert all(legacy_ph_task.get(k) for k in ("ph_bs", "ph_dos"))

    # deepcopy needed because migration changes input objects
    ph_doc = PhononBSDOSDoc.migrate_fields(**deepcopy(legacy_ph_task))
    assert_schemas_equal(ph_doc, PhononBSDOSDoc.model_config)

    # check remap of phonon DOS
    for k in ("densities", "frequencies"):
        assert np.all(
            np.abs(
                np.array(getattr(ph_doc.phonon_dos, k, []))
                - np.array(legacy_ph_task["ph_dos"].get(k, []))
            )
            < 1e-6
        )

    # check remap of phonon bandstructure
    assert np.all(
        np.abs(
            np.array(getattr(ph_doc.phonon_bandstructure, "frequencies", []))
            - np.array(legacy_ph_task["ph_bs"].get("bands", []))
        )
        < 1e-6
    )

    # check that Phonon DOS converts to CompletePhononDOS object
    assert isinstance(ph_doc.phonon_dos.to_pmg, CompletePhononDos)
    # when structure or projected DOS fields are missing, `to_pmg` returns a PhononDos object
    for k in (
        "structure",
        "projected_densities",
    ):
        model_config = deepcopy(ph_doc.model_dump())
        model_config["phonon_dos"].pop(k)
        new_task = PhononBSDOSDoc.migrate_fields(**model_config)
        assert isinstance(new_task.phonon_dos.to_pmg, PmgPhononDos)

    temps = [5, 100, 300, 500, 800]
    ref_data = {
        "entropy": [
            0.10690825310989084,
            64.92923008995054,
            118.49759120562243,
            143.87894281334866,
            167.29013558233882,
        ],
        "heat_capacity": [
            0.3096320518171239,
            47.157121712113714,
            49.56965404227773,
            49.77072796011147,
            49.8399369784691,
        ],
        "internal_energy": [
            1988.2321308731728,
            5269.03083181402,
            15060.035206972329,
            24999.080865250606,
            39943.07283219206,
        ],
        "free_energy": [
            1987.697589607624,
            -1223.8921771810346,
            -20489.242154714408,
            -46940.39054142372,
            -93889.03563367906,
        ],
    }
    tprops = ph_doc.compute_thermo_quantities(temps)
    assert all(
        t == pytest.approx(tprops["temperature"][i]) for i, t in enumerate(temps)
    )
    for k, ref_vals in ref_data.items():
        assert all(
            tprops[k][i] == pytest.approx(ref_val) for i, ref_val in enumerate(ref_vals)
        )

    # check population of structure metadata fields
    assert ph_doc.composition == ph_doc.structure.composition
    assert ph_doc.volume == ph_doc.structure.volume
    assert ph_doc.nelements == len(ph_doc.structure.composition.elements)
    assert sorted(ph_doc.elements) == sorted(ph_doc.structure.composition.elements)

    # check that crystal toolkit convenience function works
    assert ph_doc.phonon_bandstructure._to_pmg_es_bs.get_vbm()
    assert ph_doc.phonon_bandstructure._to_pmg_es_bs.get_cbm()


@pytest.mark.skipif(
    not ARROW_COMPATIBLE, reason="pyarrow must be installed to run this test."
)
def test_arrow(tmp_dir, legacy_ph_task):
    ph_doc = PhononBSDOSDoc.migrate_fields(**legacy_ph_task)
    arrow_struct = pa.scalar(
        ph_doc.model_dump(context={"format": "arrow"}), type=arrowize(PhononBSDOSDoc)
    )
    test_arrow_doc = PhononBSDOSDoc(**arrow_struct.as_py(maps_as_pydicts="strict"))
    assert test_arrow_doc

    assert ph_doc.phonon_bandstructure == test_arrow_doc.phonon_bandstructure

    # test primitive structure caching
    assert test_arrow_doc.phonon_bandstructure._primitive_structure is None
    assert isinstance(
        test_arrow_doc.phonon_bandstructure.primitive_structure, Structure
    )
    assert (
        test_arrow_doc.phonon_bandstructure._primitive_structure
        == test_arrow_doc.phonon_bandstructure.primitive_structure
    )


def test_phonopy_dos_integration(tmp_dir):
    """Test phonopy dat-file parsing."""

    temp = 0.063253
    ph_data = np.random.random((20, 2))
    ph_str = f"# Sigma = {temp}\n\t" + "\n\t".join(
        "\t".join(f"{x}" for x in row) for row in ph_data
    )

    temp_file = NamedTemporaryFile(suffix="dat", mode="w")
    temp_file.write(ph_str)
    temp_file.seek(0)
    ph_dos = PhononDOS.from_phonopy(temp_file.name)
    temp_file.close()

    for idx, attr in enumerate(["frequencies", "densities"]):
        assert np.all(np.abs(ph_data[:, idx] - np.array(getattr(ph_dos, attr))) < 1e-6)
