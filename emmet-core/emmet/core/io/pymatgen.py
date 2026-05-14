from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

_BASE_PACKAGE_NAME = "pymatgen"

_core_class_map: dict[str, str] = {
    "__version__": "core",
    "Element": "core.periodic_table",
    "Composition": "core.composition",
    "CompositionError": "core.composition",
    "formula_double_format": "util.string",
    "htmlify": "util.string",
    "latexify": "util.string",
    "latexify_spacegroup": "util.string",
    "unicodeify": "util.string",
    "Lattice": "core.lattice",
    "Specie": "core.periodic_table",
    "Species": "core.periodic_table",
    "DummySpecies": "core.periodic_table",
    "get_el_sp": "core.periodic_table",
    "PeriodicSite": "core.sites",
    "IStructure": "core.structure",
    "Structure": "core.structure",
    "StructureGraph": "core.graphs",
    "Molecule": "core.structure",
    "MoleculeGraph": "core.graphs",
    "BVAnalyzer": "core.bond_valence",
    "StructureMatcher": "core.structure_matcher",
    "ElementComparator": "core.structure_matcher",
    "AbstractComparator": "core.structure_matcher",
    "DeformStructureTransformation": "transformations.standard_transformations",
    "MoleculeMatcher": "core.molecule_matcher",
    "Trajectory": "core.trajectory",
    "SpacegroupAnalyzer": "symmetry.analyzer",
    "PointGroupAnalyzer": "symmetry.analyzer",
    "SymmetryUndeterminedError": "symmetry.analyzer",
    "Tensor": "core.tensors",
    "TensorMapping": "core.tensors",
    "SYMM_DATA": "symmetry.groups",
    "CifBlock": "io.cif",
    "CifParser": "io.cif",
    "HighSymmKpath": "symmetry.bandstructure",
    "Kpoint": "electronic_structure.bandstructure",
    "BandStructure": "electronic_structure.bandstructure",
    "BandStructureSymmLine": "electronic_structure.bandstructure",
    "Dos": "electronic_structure.dos",
    "CompleteDos": "electronic_structure.dos",
    "Spin": "electronic_structure.core",
    "Orbital": "electronic_structure.core",
    "OrbitalType": "electronic_structure.core",
    "PhononBandStructureSymmLine": "phonon.bandstructure",
    "PhononDos": "phonon.dos",
    "CompletePhononDos": "phonon.dos",
    "PhaseDiagram": "analysis.phase_diagram",
    "PhaseDiagramError": "analysis.phase_diagram",
    "IRDielectricTensor": "phonon.ir_spectra",
    "ComputedEntry": "core.entries",
    "ComputedStructureEntry": "core.entries",
    "Incar": "io.vasp.inputs",
    "Kpoints": "io.vasp.inputs",
    "Poscar": "io.vasp.inputs",
    "PotcarSingle": "io.vasp",
    "Potcar": "io.vasp.inputs",
    "Vasprun": "io.vasp.outputs",
    "BSVasprun": "io.vasp.outputs",
    "Locpot": "io.vasp.outputs",
    "Elfcar": "io.vasp.outputs",
    "Oszicar": "io.vasp.outputs",
    "Outcar": "io.vasp.outputs",
    "VolumetricData": "io.vasp.outputs",
    "Chgcar": "io.vasp.outputs",
    "VaspInputSet": "io.vasp.sets",
    "MPStaticSet": "io.vasp.sets",
    "BalancedReaction": "analysis.reaction_calculator",
    "GrainBoundary": "core.interface",
    "oxide_type": "core.structure_analyzer",
    "QCInput": "io.qchem.inputs",
    "QCOutput": "io.qchem.outputs",
    "BaseVolumetricData": "io.common",
    "bader_analysis_from_path": "command_line.bader_caller",
    "ChargemolAnalysis": "command_line.chargemol_caller",
    "BabelMolAdaptor": "io.babel",
    "NearNeighbors": "core.local_env",
    "CrystalNN": "core.local_env",
    "OpenBabelNN": "core.local_env",
    "metal_edge_extender": "core.local_env",
    "LocalStructOrderParams": "core.local_env",
    "CN_OPT_PARAMS": "core.local_env",
    "get_angle": "util.coord",
    "weisfeiler_lehman_graph_hash": "util.graph_hashing",
    "Cohp": "electronic_structure.cohp",
    "CompleteCohp": "electronic_structure.cohp",
    "LobsterCompleteDos": "electronic_structure.dos",
    "TransformedStructure": "alchemy.materials",
    "Author": "util.provenance",
    "HistoryNode": "util.provenance",
    "StructureNL": "util.provenance",
    "STRUCTURES_DIR": "util.testing",
}
"""Objects which are defined in pymatgen-core.

Can use aliases to avoid name collisions."""

_non_core_class_map: dict[str, str] = {
    "ElasticTensor": "analysis.elasticity",
    "ElasticTensorExpansion": "analysis.elasticity",
    "Deformation": "analysis.elasticity.strain",
    "Strain": "analysis.elasticity.strain",
    "Stress": "analysis.elasticity.stress",
    "AbstractElectrode": "apps.battery.battery_abc",
    "ConversionElectrode": "apps.battery.conversion_battery",
    "ConversionVoltagePair": "apps.battery.conversion_battery",
    "InsertionElectrode": "apps.battery.insertion_battery",
    "InsertionVoltagePair": "apps.battery.insertion_battery",
    "AflowPrototypeMatcher": "analysis.prototypes",
    "CollinearMagneticStructureAnalyzer": "analysis.magnetism",
    "Ordering": "analysis.magnetism.analyzer",
    "Compatibility": "analysis.compatibility",
    "MaterialsProject2020Compatibility": "analysis.compatibility",
    "MaterialsProjectAqueousCompatibility": "analysis.compatibility",
    "DiffractionPattern": "analysis.diffraction.xrd",
    "EOS": "analysis.eos",
    "EOSError": "analysis.eos",
    "AllCoordinationGeometries": "analysis.chemenv.coordination_environments.coordination_geometries",
    "LightStructureEnvironments": "analysis.chemenv.coordination_environments.structure_environments",
    "SimplestChemenvStrategy": "analysis.chemenv.coordination_environments.chemenv_strategies",
    "LocalGeometryFinder": "analysis.chemenv.coordination_environments.coordination_geometry_finder",
    "MaterialsProjectDFTMixingScheme": "entries.mixing_scheme",
    "PiezoTensor": "analysis.piezo",
    "WAVELENGTHS": "analysis.diffraction.xrd",
    "XRDCalculator": "analysis.diffraction.xrd",
    "XAS": "analysis.xas.spectrum",
    "site_weighted_spectrum": "analysis.xas.spectrum",
    "get_structure_components": "analysis.dimensionality",
}
"""Objects which are defined only in pymatgen, and not pymatgen-core.

Can use aliases to avoid name collisions."""

_add_on_class_map: dict[str, str] = {
    # pymatgen-analysis-alloys add-on
    "AlloyMember": "analysis.alloys.core",
    "AlloyPair": "analysis.alloys.core",
    "AlloySystem": "analysis.alloys.core",
    # pymatgen-analysis-diffusion add-on
    "MigrationGraph": "analysis.diffusion.neb.full_path_mapper",
    "add_edge_data_from_sc": "analysis.diffusion.utils.edge_data_from_sc",
    "get_sc_fromstruct": "analysis.diffusion.utils.supercells",
    "get_start_end_structures": "analysis.diffusion.utils.supercells",
    # pymatgen-io-validation add-on
    "REQUIRED_VASP_FILES": "io.validation.validation",
    "VaspValidator": "io.validation.validation",
    "LightOutcar": "io.validation.common",
    "LightVasprun": "io.validation.common",
    "PotcarSummaryStats": "io.validation.common",
    "VaspFiles": "io.validation.common",
    "VaspInputSafe": "io.validation.common",
    "get_kpoint_divisions_from_kspacing": "io.validation.check_kpoints_kspacing",
    # pymatgen-analysis-defects add-on
    "Defect": "analysis.defects.core",
    # pymatgen-io-lobster add-on
    "Bandoverlaps": "io.lobster",
    "Charge": "io.lobster",
    "Doscar": "io.lobster",
    "Grosspop": "io.lobster",
    "Icohplist": "io.lobster",
    "Lobsterin": "io.lobster",
    "Lobsterout": "io.lobster",
    "MadelungEnergies": "io.lobster",
    "SitePotential": "io.lobster",
}
"""Objects which are defined in pymatgen add-ons.

Can use aliases to avoid name collisions."""

_class_map: dict[str, str] = {
    **_core_class_map,
    **_non_core_class_map,
    **_add_on_class_map,
}
"""Dict of object names to their base import string.

Can use aliases to avoid name collisions."""

_name_collision_aliases: dict[str, str] = {"BaseVolumetricData": "VolumetricData"}
"""Aliases for classes to avoid name collisions."""


def __getattr__(name: str) -> Any:
    """Lazily load objects from pymatgen."""
    if name in _class_map:
        return getattr(
            import_module(f"{_BASE_PACKAGE_NAME}.{_class_map[name]}"),
            _name_collision_aliases.get(name, name),
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> Sequence[str]:
    """List available interfaces to pymatgen objects."""
    return sorted(
        ".".join(
            (_BASE_PACKAGE_NAME, base_import, _name_collision_aliases.get(name, name))
        )
        for name, base_import in _class_map.items()
    )
