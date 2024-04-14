import pytest


from maggma.stores import MemoryStore, JSONStore
from emmet.builders.classical_md.openmm.core import ElectrolyteBuilder


@pytest.fixture()
def solute_store():
    return MemoryStore(key="job_uuid")


@pytest.fixture()
def water_stores(test_dir, tmp_path):
    # intended to only be run locally in a dev environment
    recreate_input = False

    stores_dir = test_dir / "classical_md" / "water_stores"
    md_doc_store = JSONStore(
        str(stores_dir / "docs_store.json"), read_only=False, key="uuid"
    )
    blob_store = JSONStore(
        str(stores_dir / "blob_store.json"), read_only=False, key="blob_uuid"
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
            n_steps=100, traj_interval=10, state_interval=10, name="nvt1"
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


def test_builder(water_stores, solute_store):
    doc_store, blob_store = water_stores
    builder = ElectrolyteBuilder(doc_store, blob_store, solute_store)

    builder.connect()
    items = builder.get_items()
    processed_docs = builder.process_items(items)
    builder.update_targets(processed_docs)

    print("hello")
    return
