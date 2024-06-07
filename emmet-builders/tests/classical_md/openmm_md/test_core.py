import pytest
from MDAnalysis import Universe
from solvation_analysis.solute import Solute

from maggma.stores import MemoryStore, JSONStore
from emmet.builders.classical_md.openmm.core import ElectrolyteBuilder
from emmet.builders.classical_md.utils import (
    create_solute,
    identify_solute,
    identify_networking_solvents,
)


@pytest.fixture()
def solute_store():
    return MemoryStore(key="job_uuid")


@pytest.fixture()
def calculations_store():
    return MemoryStore(key="job_uuid")


@pytest.fixture()
def water_stores(test_dir, tmp_path):
    # intended to only be run locally in a dev environment
    recreate_input = False

    stores_dir = test_dir / "classical_md" / "water_stores"

    read_only = not recreate_input
    md_doc_store = JSONStore(
        str(stores_dir / "docs_store.json"), read_only=read_only, key="uuid"
    )
    blob_store = JSONStore(
        str(stores_dir / "blob_store.json"), read_only=read_only, key="blob_uuid"
    )

    if recreate_input:
        from atomate2.classical_md.core import generate_interchange
        from atomate2.classical_md.utils import create_mol_spec
        from atomate2.classical_md.openmm.jobs import NVTMaker, NPTMaker
        from jobflow import run_locally, JobStore

        # delete old stores
        for store_file in stores_dir.glob("*.json"):
            store_file.unlink()

        mol_specs = [
            create_mol_spec("CCO", 10, name="ethanol"),
            create_mol_spec("O", 400, name="water"),
            create_mol_spec("[Na+]", 400, name="Na"),
            create_mol_spec("[Br-]", 400, name="Br"),
        ]

        interchange_job = generate_interchange(mol_specs, 0.8)

        nvt1 = NPTMaker(
            n_steps=100, traj_interval=10, state_interval=10, name="npt1"
        ).make(
            interchange_job.output.interchange,
            prev_task=interchange_job.output,
            output_dir=tmp_path,
        )

        nvt2 = NVTMaker(name="nvt2", n_steps=100, embed_traj=True).make(
            nvt1.output.interchange,
            prev_task=nvt1.output,
            output_dir=tmp_path,
        )

        nvt3 = NVTMaker(name="nvt3", n_steps=100).make(
            nvt2.output.interchange,
            prev_task=nvt2.output,
            output_dir=tmp_path,
        )

        wf = [interchange_job, nvt1, nvt2, nvt3]
        run_locally(
            wf,
            store=JobStore(md_doc_store, additional_stores={"data": blob_store}),
            ensure_success=True,
        )

    return md_doc_store, blob_store


def test_builder(water_stores, solute_store, calculations_store):
    doc_store, blob_store = water_stores
    builder = ElectrolyteBuilder(
        doc_store, blob_store, solute_store, calculations_store
    )

    builder.connect()
    items = builder.get_items()
    processed_docs = builder.process_items(items)
    builder.update_targets(processed_docs)

    solute_doc = solute_store.query_one()
    assert len(solute_doc["coordination_numbers"]) == 3

    calculations_doc = calculations_store.query_one()
    assert calculations_doc["calc_types"] == ["NPTMaker", "NVTMaker", "NVTMaker"]
    assert calculations_doc["steps"] == [100, 100, 100]


def test_instantiate_universe(water_stores, solute_store, tmp_path):
    doc_store, blob_store = water_stores
    builder = ElectrolyteBuilder(doc_store, blob_store, solute_store)
    builder.connect()

    u = builder.instantiate_universe("da21514c-7c40-4f00-a85f-0b176e90c4ec", tmp_path)

    assert isinstance(u, Universe)

    solute = create_solute(
        u,
        solute_name=identify_solute(u),
        networking_solvents=identify_networking_solvents(u),
        fallback_radius=3,
    )
    solute.run()

    assert isinstance(solute, Solute)
