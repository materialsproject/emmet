import pytest

from MDAnalysis import Universe
from solvation_analysis.solute import Solute
import numpy as np

from maggma.stores import MemoryStore, JSONStore
from emmet.builders.classical_md.openmm.core import (
    ElectrolyteBuilder,
    BenchmarkingBuilder,
)
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
def benchmarking_store():
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
            create_mol_spec("CCO", 10, name="ethanol", charge_method="mmff94"),
            create_mol_spec("O", 400, name="water", charge_method="mmff94"),
            create_mol_spec("[Na+]", 400, name="Na", charge_method="mmff94"),
            create_mol_spec("[Br-]", 400, name="Br", charge_method="mmff94"),
        ]

        interchange_job = generate_interchange(mol_specs, 0.8)

        npt1 = NPTMaker(
            n_steps=100, traj_interval=10, state_interval=10, name="npt1"
        ).make(
            interchange_job.output.interchange,
            prev_task=interchange_job.output,
        )

        nvt2 = NVTMaker(name="nvt2", n_steps=100, embed_traj=True).make(
            npt1.output.interchange,
            prev_task=npt1.output,
        )

        nvt3 = NVTMaker(name="nvt3", n_steps=100).make(
            nvt2.output.interchange,
            prev_task=nvt2.output,
        )

        wf = [interchange_job, npt1, nvt2, nvt3]
        run_locally(
            wf,
            store=JobStore(md_doc_store, additional_stores={"data": blob_store}),
            ensure_success=True,
            root_dir=tmp_path,
        )

    return md_doc_store, blob_store


@pytest.fixture()
def cco_stores(test_dir, tmp_path):
    # intended to only be run locally in a dev environment
    recreate_input = False

    stores_dir = test_dir / "classical_md" / "cco_stores"

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
        from atomate2.classical_md.openmm.jobs import NVTMaker
        from jobflow import run_locally, JobStore

        # delete old stores
        for store_file in stores_dir.glob("*.json"):
            store_file.unlink()

        mol_specs = [
            create_mol_spec("CCO", 200, name="ethanol", charge_method="mmff94"),
        ]

        interchange_job = generate_interchange(mol_specs, 0.8)

        nvt1 = NVTMaker(
            name="nvt1",
            n_steps=200,
            traj_interval=10,
            state_interval=10,
            embed_traj=True,
            report_velocities=True,
            traj_file_type="h5md",
        ).make(
            interchange_job.output.interchange,
            prev_task=interchange_job.output,
        )

        nvt2 = NVTMaker(
            name="nvt2",
            n_steps=200,
            traj_interval=10,
            state_interval=10,
            embed_traj=True,
            report_velocities=True,
            traj_file_type="h5md",
        ).make(
            nvt1.output.interchange,
            prev_task=nvt1.output,
        )

        wf = [
            interchange_job,
            nvt1,
            nvt2,
        ]
        run_locally(
            wf,
            store=JobStore(md_doc_store, additional_stores={"data": blob_store}),
            ensure_success=True,
            root_dir=tmp_path,
        )

    return md_doc_store, blob_store


def test_electrolyte_builder(water_stores, solute_store, calculations_store):
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


def test_electrolyte_builder_local(
    water_stores, solute_store, calculations_store, test_dir
):
    doc_store, blob_store = water_stores
    builder = ElectrolyteBuilder(
        doc_store, blob_store, solute_store, calculations_store
    )

    builder.connect()
    items = builder.get_items(local_trajectories=True)

    # needed because files are generated locally
    for calc in items[0]["output"]["calcs_reversed"]:
        calc["dir_name"] = str(test_dir / "classical_md" / "water_system")

    processed_docs = builder.process_items(items, local_trajectories=True)
    builder.update_targets(processed_docs)

    solute_doc = solute_store.query_one()
    assert len(solute_doc["coordination_numbers"]) == 3

    calculations_doc = calculations_store.query_one()
    assert calculations_doc["calc_types"] == ["NPTMaker", "NVTMaker", "NVTMaker"]
    assert calculations_doc["steps"] == [100, 100, 100]


def test_benchmarking_builder(cco_stores, benchmarking_store):
    doc_store, blob_store = cco_stores
    builder = BenchmarkingBuilder(
        doc_store,
        blob_store,
        benchmarking_store,
    )

    builder.connect()
    items = builder.get_items()
    processed_docs = builder.process_items(items)
    builder.update_targets(processed_docs)

    benchmarking_doc = benchmarking_store.query_one()
    assert np.isclose(benchmarking_doc["density"], 0.8)


def test_instantiate_universe(water_stores, solute_store, tmp_path):
    doc_store, blob_store = water_stores
    builder = ElectrolyteBuilder(doc_store, blob_store, solute_store)
    builder.connect()
    job_uuid = doc_store.query_one({"name": "nvt3"})["uuid"]

    u = builder.instantiate_universe(job_uuid, tmp_path)

    assert isinstance(u, Universe)

    solute = create_solute(
        u,
        solute_name=identify_solute(u),
        networking_solvents=identify_networking_solvents(u),
        fallback_radius=3,
    )
    solute.run()

    assert isinstance(solute, Solute)
