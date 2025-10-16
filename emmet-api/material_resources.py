import os

from pymongo import AsyncMongoClient

from emmet.api.core.settings import MAPISettings
from emmet.api.resource.utils import CollectionWithKey

resources = {}

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

    materials_store = CollectionWithKey(suffix_db["materials"])
    absorption_store = CollectionWithKey(suffix_db["absorption"])
    bonds_store = CollectionWithKey(suffix_db["bonds"])
    chemenv_store = CollectionWithKey(suffix_db["chemenv"])
    thermo_store = CollectionWithKey(suffix_db["thermo"], "thermo_id")
    dielectric_store = CollectionWithKey(suffix_db["dielectric"])
    piezoelectric_store = CollectionWithKey(suffix_db["piezoelectric"])
    magnetism_store = CollectionWithKey(suffix_db["magnetism"])
    phonon_bs_store = CollectionWithKey(suffix_db["phonon"])
    elasticity_store = CollectionWithKey(suffix_db["elasticity"])
    formula_autocomplete_store = CollectionWithKey(
        core_db["formula_autocomplete"], "_id"
    )
    task_store = CollectionWithKey(tasks_db["tasks"], "task_id")
    eos_store = CollectionWithKey(core_db["eos"], "task_id")
    similarity_store = CollectionWithKey(core_db["similarity"])
    xas_store = CollectionWithKey(core_db["xas"], "spectrum_id")
    gb_store = CollectionWithKey(core_db["grain_boundaries"], "task_id")
    fermi_store = CollectionWithKey(core_db["fermi_surface"], "task_id")
    doi_store = CollectionWithKey(core_db["dois"])
    substrates_store = CollectionWithKey(core_db["substrates"], "film_id")
    surface_props_store = CollectionWithKey(core_db["surface_properties"], "task_id")
    robo_store = CollectionWithKey(suffix_db["robocrys"])
    synth_store = CollectionWithKey(core_db["synth_descriptions"], "_id")
    insertion_electrodes_store = CollectionWithKey(
        suffix_db["insertion_electrodes"], "battery_id"
    )
    conversion_electrodes_store = CollectionWithKey(
        suffix_db["conversion_electrodes"], "battery_id"
    )
    oxi_states_store = CollectionWithKey(suffix_db["oxi_states"])
    provenance_store = CollectionWithKey(suffix_db["provenance"])
    alloy_pairs_store = CollectionWithKey(suffix_db["alloys"], "pair_id")
    summary_store = CollectionWithKey(suffix_db["summary"])
    es_store = CollectionWithKey(suffix_db["electronic_structure"])
    mpcomplete_store = CollectionWithKey(consumer_db["mpcomplete"], "submission_id")
    consumer_settings_store = CollectionWithKey(consumer_db["settings"], "consumer_id")
    messages_store = CollectionWithKey(consumer_db["messages"], "title")
    general_store = CollectionWithKey(consumer_db["general_store"], "submission_id")

else:
    raise RuntimeError("Must specify MongoDB URI containing inputs.")

# Materials
from emmet.api.routes.materials.materials.resources import (
    find_structure_resource,
    formula_autocomplete_resource,
    blessed_tasks_resource,
    materials_resource,
)

materials_resources = list()

materials_resources.extend(
    [
        blessed_tasks_resource(materials_store),
        find_structure_resource(materials_store),
        formula_autocomplete_resource(formula_autocomplete_store),
        materials_resource(materials_store),
    ]
)

# Absorption
from emmet.api.routes.materials.absorption.resources import absorption_resource

materials_resources.extend([absorption_resource(absorption_store)])

# Bonds
from emmet.api.routes.materials.bonds.resources import bonds_resource

materials_resources.extend([bonds_resource(bonds_store)])

# Chemenv
from emmet.api.routes.materials.chemenv.resources import chemenv_resource

materials_resources.extend([chemenv_resource(chemenv_store)])

# Tasks
from emmet.api.routes.materials.tasks.resources import (
    entries_resource,
    task_deprecation_resource,
    task_resource,
    trajectory_resource,
)

materials_resources.extend(
    [
        trajectory_resource(task_store),
        entries_resource(task_store),
        task_deprecation_resource(materials_store),
        task_resource(task_store),
    ]
)

# Thermo
from emmet.api.routes.materials.thermo.resources import thermo_resource

materials_resources.extend([thermo_resource(thermo_store)])

# Dielectric
from emmet.api.routes.materials.dielectric.resources import dielectric_resource

materials_resources.extend([dielectric_resource(dielectric_store)])

# Piezoelectric
from emmet.api.routes.materials.piezo.resources import piezo_resource

materials_resources.extend([piezo_resource(piezoelectric_store)])

# Magnetism
from emmet.api.routes.materials.magnetism.resources import magnetism_resource

materials_resources.extend([magnetism_resource(magnetism_store)])

# Phonon
from emmet.api.routes.materials.phonon.resources import phonon_bsdos_resource

materials_resources.extend([phonon_bsdos_resource(phonon_bs_store)])

# EOS
from emmet.api.routes.materials.eos.resources import eos_resource

materials_resources.extend([eos_resource(eos_store)])

# Similarity
from emmet.api.routes.materials.similarity.resources import similarity_resource

materials_resources.extend([similarity_resource(similarity_store)])

# XAS
from emmet.api.routes.materials.xas.resources import xas_resource

materials_resources.extend([xas_resource(xas_store)])

# Grain Boundaries
from emmet.api.routes.materials.grain_boundary.resources import gb_resource

materials_resources.extend([gb_resource(gb_store)])

# Fermi Surface
from emmet.api.routes.materials.fermi.resources import fermi_resource

materials_resources.extend([fermi_resource(fermi_store)])

# Elasticity
from emmet.api.routes.materials.elasticity.resources import elasticity_resource

materials_resources.extend([elasticity_resource(elasticity_store)])

# Substrates
from emmet.api.routes.materials.substrates.resources import substrates_resource

materials_resources.extend([substrates_resource(substrates_store)])

# Surface Properties
from emmet.api.routes.materials.surface_properties.resources import (
    surface_props_resource,
)

materials_resources.extend([surface_props_resource(surface_props_store)])


# Robocrystallographer
from emmet.api.routes.materials.robocrys.resources import (
    robo_resource,
    robo_search_resource,
)

materials_resources.extend(
    [robo_search_resource(robo_store), robo_resource(robo_store)]
)

# Synthesis
from emmet.api.routes.materials.synthesis.resources import synth_resource

materials_resources.extend([synth_resource(synth_store)])

# Electrodes
from emmet.api.routes.materials.insertion_electrodes.resources import (
    insertion_electrodes_resource,
)

materials_resources.extend([insertion_electrodes_resource(insertion_electrodes_store)])


from emmet.api.routes.materials.conversion_electrodes.resources import (
    conversion_electrodes_resource,
)

materials_resources.extend(
    [conversion_electrodes_resource(conversion_electrodes_store)]
)

# Oxidation States
from emmet.api.routes.materials.oxidation_states.resources import oxi_states_resource

materials_resources.extend([oxi_states_resource(oxi_states_store)])

# Alloys
from emmet.api.routes.materials.alloys.resources import alloy_pairs_resource

materials_resources.extend([alloy_pairs_resource(alloy_pairs_store)])

# Provenance
from emmet.api.routes.materials.provenance.resources import provenance_resource

materials_resources.extend([provenance_resource(provenance_store)])

# Summary
from emmet.api.routes.materials.summary.resources import (
    summary_resource,
    summary_stats_resource,
)

materials_resources.extend(
    [summary_stats_resource(summary_store), summary_resource(summary_store)]
)

# Electronic Structure
from emmet.api.routes.materials.electronic_structure.resources import (
    bs_resource,
    dos_resource,
    es_resource,
)

materials_resources.extend(
    [
        bs_resource(es_store),
        dos_resource(es_store),
        es_resource(es_store),
    ]
)

# MPComplete
from emmet.api.routes.materials.mpcomplete.resources import mpcomplete_resource

resources.update({"mpcomplete": [mpcomplete_resource(mpcomplete_store)]})

# DOIs
from emmet.api.routes.dois.resources import dois_resource

resources.update({"doi": [dois_resource(doi_store)]})

# Consumers
from emmet.api.routes._consumer.resources import settings_resource

resources.update({"_user_settings": [settings_resource(consumer_settings_store)]})

# Messages
from emmet.api.routes._messages.resources import messages_resource

resources.update({"_messages": [messages_resource(messages_store)]})

# General Store
from emmet.api.routes._general_store.resources import general_store_resource

resources.update({"_general_store": [general_store_resource(general_store)]})

resources.update({"materials": materials_resources})
