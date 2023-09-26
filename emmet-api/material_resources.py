import os

from maggma.stores import MongoURIStore, S3Store

from emmet.api.core.settings import MAPISettings

resources = {}

default_settings = MAPISettings()

db_uri = os.environ.get("MPCONTRIBS_MONGO_HOST", None)
db_version = default_settings.DB_VERSION
db_suffix = os.environ["MAPI_DB_NAME_SUFFIX"]

if db_uri:
    # allow db_uri to be set with a different protocol scheme
    # but prepend with mongodb+srv:// if not otherwise specified
    if len(db_uri.split("://", 1)) < 2:
        db_uri = "mongodb+srv://" + db_uri

    materials_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="material_id",
        collection_name="materials",
    )

    absorption_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="material_id",
        collection_name="absorption",
    )

    bonds_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="material_id",
        collection_name="bonds",
    )

    chemenv_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="material_id",
        collection_name="chemenv",
    )

    formula_autocomplete_store = MongoURIStore(
        uri=db_uri,
        database="mp_core",
        key="_id",
        collection_name="formula_autocomplete",
    )

    task_store = MongoURIStore(
        uri=db_uri, database="mp_core", key="task_id", collection_name="tasks"
    )

    thermo_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="thermo_id",
        collection_name="thermo",
    )

    s3_phase_diagram_index = MongoURIStore(
        uri=db_uri,
        database="mp_core",
        key="phase_diagram_id",
        collection_name="s3_phase_diagram_index",
    )

    phase_diagram_store = S3Store(
        index=s3_phase_diagram_index,
        bucket="mp-phase-diagrams",
        s3_workers=24,
        key="phase_diagram_id",
        searchable_fields=["chemsys", "thermo_type", "phase_diagram_id"],
        compress=True,
    )

    dielectric_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="material_id",
        collection_name="dielectric",
    )

    piezoelectric_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="material_id",
        collection_name="piezoelectric",
    )

    magnetism_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="material_id",
        collection_name="magnetism",
    )

    phonon_bs_store = MongoURIStore(
        uri=db_uri, database="mp_core", key="material_id", collection_name="pmg_ph_bs"
    )

    eos_store = MongoURIStore(
        uri=db_uri, database="mp_core", key="task_id", collection_name="eos"
    )

    similarity_store = MongoURIStore(
        uri=db_uri, database="mp_core", key="material_id", collection_name="similarity"
    )

    xas_store = MongoURIStore(
        uri=db_uri, database="mp_core", key="spectrum_id", collection_name="xas"
    )

    gb_store = MongoURIStore(
        uri=db_uri,
        database="mp_core",
        key="task_id",
        collection_name="grain_boundaries",
    )

    fermi_store = MongoURIStore(
        uri=db_uri, database="mp_core", key="task_id", collection_name="fermi_surface"
    )

    elasticity_store = MongoURIStore(
        uri=db_uri, database="mp_core", key="task_id", collection_name="elasticity"
    )

    doi_store = MongoURIStore(
        uri=db_uri, database="mp_core", key="task_id", collection_name="dois"
    )

    substrates_store = MongoURIStore(
        uri=db_uri, database="mp_core", key="film_id", collection_name="substrates"
    )

    surface_props_store = MongoURIStore(
        uri=db_uri,
        database="mp_core",
        key="task_id",
        collection_name="surface_properties",
    )

    robo_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="material_id",
        collection_name="robocrys",
    )

    synth_store = MongoURIStore(
        uri=db_uri, database="mp_core", key="_id", collection_name="synth_descriptions"
    )

    insertion_electrodes_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="battery_id",
        collection_name="insertion_electrodes",
    )

    conversion_electrodes_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="battery_id",
        collection_name="conversion_electrodes",
    )

    oxi_states_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="material_id",
        collection_name="oxi_states",
    )

    provenance_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="material_id",
        collection_name="provenance",
    )

    alloy_pairs_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="pair_id",
        collection_name="alloy_pairs",
    )

    summary_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="material_id",
        collection_name="summary",
    )

    es_store = MongoURIStore(
        uri=db_uri,
        database=f"mp_core_{db_suffix}",
        key="material_id",
        collection_name="electronic_structure",
    )

    s3_bs_index = MongoURIStore(
        uri=db_uri,
        database="mp_core",
        key="fs_id",
        collection_name="s3_bandstructure_index",
    )

    s3_dos_index = MongoURIStore(
        uri=db_uri, database="mp_core", key="fs_id", collection_name="s3_dos_index"
    )

    s3_bs = S3Store(
        index=s3_bs_index,
        bucket="mp-bandstructures",
        compress=True,
        key="fs_id",
        unpack_data=False,
        searchable_fields=["task_id", "fs_id"],
    )

    s3_dos = S3Store(
        index=s3_dos_index,
        bucket="mp-dos",
        compress=True,
        key="fs_id",
        unpack_data=False,
        searchable_fields=["task_id", "fs_id"],
    )

    s3_chgcar_index = MongoURIStore(
        uri=db_uri,
        database="mp_core",
        key="fs_id",
        collection_name="atomate_chgcar_fs_index",
    )

    s3_chgcar = S3Store(
        index=s3_chgcar_index,
        bucket="mp-volumetric",
        sub_dir="atomate_chgcar_fs/",
        compress=True,
        key="fs_id",
        unpack_data=False,
        searchable_fields=["task_id", "fs_id"],
    )

    chgcar_url = MongoURIStore(
        uri=db_uri, database="mp_core", key="fs_id", collection_name="chgcar_s3_urls"
    )

    mpcomplete_store = MongoURIStore(
        uri=db_uri,
        database="mp_consumers",
        key="submission_id",
        collection_name="mpcomplete",
    )

    consumer_settings_store = MongoURIStore(
        uri=db_uri,
        database="mp_consumers",
        key="consumer_id",
        collection_name="settings",
    )

    general_store = MongoURIStore(
        uri=db_uri,
        database="mp_consumers",
        key="submission_id",
        collection_name="general_store",
    )

    messages_store = MongoURIStore(
        uri=db_uri,
        database="mp_consumers",
        key="title",
        collection_name="messages",
    )
else:
    raise RuntimeError("Must specify MongoDB URI containing inputs.")

# Materials
from emmet.api.routes.materials.materials.resources import (
    find_structure_resource,
    formula_autocomplete_resource,
    materials_resource,
)

materials_resources = list()

materials_resources.extend(
    [
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
from emmet.api.routes.materials.thermo.resources import (
    phase_diagram_resource,
    thermo_resource,
)

materials_resources.extend(
    [phase_diagram_resource(phase_diagram_store), thermo_resource(thermo_store)]
)

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

# Charge Density
from emmet.api.routes.materials.charge_density.resources import (
    charge_density_resource,
    charge_density_url_resource,
)

materials_resources.extend(
    [charge_density_resource(s3_chgcar), charge_density_url_resource(chgcar_url)]
)

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
    bs_obj_resource,
    bs_resource,
    dos_obj_resource,
    dos_resource,
    es_resource,
)

materials_resources.extend(
    [
        bs_resource(es_store),
        dos_resource(es_store),
        es_resource(es_store),
        bs_obj_resource(s3_bs),
        dos_obj_resource(s3_dos),
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
