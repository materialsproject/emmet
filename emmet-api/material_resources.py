import os

from pymongo import AsyncMongoClient

from emmet.api.core.settings import MAPISettings
from emmet.api.resource.utils import CollectionWithKey
from emmet.api.routes._consumer.resources import settings_resource
from emmet.api.routes._general_store.resources import general_store_resource
from emmet.api.routes._messages.resources import messages_resource
from emmet.api.routes.dois.resources import dois_resource
from emmet.api.routes.materials.absorption.resources import absorption_resource
from emmet.api.routes.materials.alloys.resources import alloy_pairs_resource
from emmet.api.routes.materials.bonds.resources import bonds_resource
from emmet.api.routes.materials.chemenv.resources import chemenv_resource
from emmet.api.routes.materials.conversion_electrodes.resources import (
    conversion_electrodes_resource,
)
from emmet.api.routes.materials.dielectric.resources import dielectric_resource
from emmet.api.routes.materials.elasticity.resources import elasticity_resource
from emmet.api.routes.materials.electronic_structure.resources import (
    bs_resource,
    dos_resource,
    es_resource,
)
from emmet.api.routes.materials.eos.resources import eos_resource
from emmet.api.routes.materials.grain_boundary.resources import gb_resource
from emmet.api.routes.materials.insertion_electrodes.resources import (
    insertion_electrodes_resource,
)
from emmet.api.routes.materials.magnetism.resources import magnetism_resource
from emmet.api.routes.materials.materials.resources import (
    blessed_tasks_resource,
    find_structure_resource,
    formula_autocomplete_resource,
    materials_resource,
)
from emmet.api.routes.materials.mpcomplete.resources import mpcomplete_resource
from emmet.api.routes.materials.oxidation_states.resources import oxi_states_resource
from emmet.api.routes.materials.phonon.resources import phonon_bsdos_resource
from emmet.api.routes.materials.piezo.resources import piezo_resource
from emmet.api.routes.materials.provenance.resources import provenance_resource
from emmet.api.routes.materials.robocrys.resources import (
    robo_resource,
    robo_search_resource,
)
from emmet.api.routes.materials.similarity.resources import (
    similarity_feature_vector_resource,
    similarity_resource,
)
from emmet.api.routes.materials.substrates.resources import substrates_resource
from emmet.api.routes.materials.summary.resources import summary_resource
from emmet.api.routes.materials.surface_properties.resources import (
    surface_props_resource,
)
from emmet.api.routes.materials.synthesis.resources import synth_resource
from emmet.api.routes.materials.tasks.resources import entries_resource, task_resource
from emmet.api.routes.materials.thermo.resources import thermo_resource
from emmet.api.routes.materials.xas.resources import xas_resource

default_settings = MAPISettings()  # type: ignore
db_uri = os.environ.get("MPMATERIALS_MONGO_HOST", None)
db_uri_tasks = os.environ.get("MPTASKS_MONGO_HOST", db_uri)
db_version = default_settings.DB_VERSION
db_suffix = os.environ["MAPI_DB_NAME_SUFFIX"]
if db_uri:
    # allow db_uri to be set with a different protocol scheme
    # but prepend with mongodb+srv:// if not otherwise specified
    if len(db_uri.split("://", 1)) < 2:
        db_uri = "mongodb+srv://" + db_uri
    if len(db_uri_tasks.split("://", 1)) < 2:
        db_uri_tasks = "mongodb+srv://" + db_uri_tasks

    mongo_client = AsyncMongoClient(db_uri)

    suffix_db = mongo_client[f"mp_core_{db_suffix}"]
    core_db = mongo_client["mp_core"]
    consumer_db = mongo_client["mp_consumers"]

    tasks_mongo_client = AsyncMongoClient(db_uri_tasks)
    tasks_db = tasks_mongo_client["mp_core"]

    absorption_store = CollectionWithKey(suffix_db["absorption"])
    alloy_pairs_store = CollectionWithKey(suffix_db["alloys"], "pair_id")
    bonds_store = CollectionWithKey(suffix_db["bonds"])
    chemenv_store = CollectionWithKey(suffix_db["chemenv"])
    consumer_settings_store = CollectionWithKey(consumer_db["settings"], "consumer_id")
    conversion_electrodes_store = CollectionWithKey(
        suffix_db["conversion_electrodes"], "battery_id"
    )
    dielectric_store = CollectionWithKey(suffix_db["dielectric"])
    doi_store = CollectionWithKey(core_db["dois"])
    elasticity_store = CollectionWithKey(suffix_db["elasticity"])
    eos_store = CollectionWithKey(core_db["eos_legacy"], "task_id")
    es_store = CollectionWithKey(suffix_db["electronic_structure"])
    formula_autocomplete_store = CollectionWithKey(
        core_db["formula_autocomplete"], "_id"
    )
    gb_store = CollectionWithKey(core_db["grain_boundaries_legacy"], "task_id")
    general_store = CollectionWithKey(consumer_db["general_store"], "submission_id")
    insertion_electrodes_store = CollectionWithKey(
        suffix_db["insertion_electrodes"], "battery_id"
    )
    magnetism_store = CollectionWithKey(suffix_db["magnetism"])
    materials_store = CollectionWithKey(suffix_db["materials"])
    messages_store = CollectionWithKey(consumer_db["messages"], "title")
    mpcomplete_store = CollectionWithKey(consumer_db["mpcomplete"], "submission_id")
    oxi_states_store = CollectionWithKey(suffix_db["oxidation_states"])
    phonon_bs_store = CollectionWithKey(core_db["phonon"])
    piezoelectric_store = CollectionWithKey(suffix_db["piezoelectric"])
    provenance_store = CollectionWithKey(suffix_db["provenance"])
    robo_store = CollectionWithKey(suffix_db["robocrys"])
    similarity_store = CollectionWithKey(core_db["similarity_crystalnn_2026_05_14"])
    substrates_store = CollectionWithKey(core_db["substrates"], "film_id")
    summary_store = CollectionWithKey(suffix_db["summary"])
    surface_props_store = CollectionWithKey(
        core_db["surface_properties_legacy"], "task_id"
    )
    synth_store = CollectionWithKey(core_db["synth_descriptions"], "_id")
    task_store = CollectionWithKey(tasks_db["tasks"], "task_id")
    thermo_store = CollectionWithKey(suffix_db["thermo"], "thermo_id")
    xas_store = CollectionWithKey(core_db["xas_legacy"], "spectrum_id")
else:
    raise RuntimeError("Must specify MongoDB URI containing inputs.")

materials_resources = [
    absorption_resource(absorption_store),
    alloy_pairs_resource(alloy_pairs_store),
    blessed_tasks_resource(materials_store),
    bonds_resource(bonds_store),
    bs_resource(es_store),
    chemenv_resource(chemenv_store),
    conversion_electrodes_resource(conversion_electrodes_store),
    dielectric_resource(dielectric_store),
    dos_resource(es_store),
    elasticity_resource(elasticity_store),
    entries_resource(task_store),
    eos_resource(eos_store),
    es_resource(es_store),
    find_structure_resource(materials_store),
    formula_autocomplete_resource(formula_autocomplete_store),
    gb_resource(gb_store),
    insertion_electrodes_resource(insertion_electrodes_store),
    magnetism_resource(magnetism_store),
    materials_resource(materials_store),
    oxi_states_resource(oxi_states_store),
    phonon_bsdos_resource(phonon_bs_store),
    piezo_resource(piezoelectric_store),
    provenance_resource(provenance_store),
    robo_resource(robo_store),
    robo_search_resource(robo_store),
    similarity_feature_vector_resource(similarity_store),
    similarity_resource(similarity_store),
    substrates_resource(substrates_store),
    summary_resource(summary_store),
    surface_props_resource(surface_props_store),
    synth_resource(synth_store),
    task_resource(task_store),
    thermo_resource(thermo_store),
    xas_resource(xas_store),
]

resources = {
    "_general_store": [general_store_resource(general_store)],
    "_messages": [messages_resource(messages_store)],
    "_user_settings": [settings_resource(consumer_settings_store)],
    "doi": [dois_resource(doi_store)],
    "materials": materials_resources,
    "mpcomplete": [mpcomplete_resource(mpcomplete_store)],
}
