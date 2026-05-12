from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

_BASE_PACKAGE_NAME = "pymatgen"

_class_map: dict[str, str] = {
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
    "BVAnalyzer": "analysis.bond_valence",
    "StructureMatcher": "analysis.structure_matcher",
    "ElementComparator": "analysis.structure_matcher",
    "AbstractComparator": "analysis.structure_matcher",
    "DeformStructureTransformation": "transformations.standard_transformations",
    "MoleculeMatcher": "analysis.molecule_matcher",
    "Trajectory": "core.trajectory",
    "SpacegroupAnalyzer": "symmetry.analyzer",
    "PointGroupAnalyzer": "symmetry.analyzer",
    "SymmetryUndeterminedError": "symmetry.analyzer",
    "EOS": "analysis.eos",
    "EOSError": "analysis.eos",
    "PiezoTensor": "analysis.piezo",
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
    "XAS": "analysis.xas.spectrum",
    "site_weighted_spectrum": "analysis.xas.spectrum",
    "PhaseDiagram": "analysis.phase_diagram",
    "PhaseDiagramError": "analysis.phase_diagram",
    "IRDielectricTensor": "phonon.ir_spectra",
    "ComputedEntry": "core.entries",
    "ComputedStructureEntry": "core.entries",
    "Compatibility": "analysis.compatibility",
    "MaterialsProject2020Compatibility": "analysis.compatibility",
    "MaterialsProjectAqueousCompatibility": "analysis.compatibility",
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
    "DiffractionPattern": "analysis.diffraction.xrd",
    "MaterialsProjectDFTMixingScheme": "entries.mixing_scheme",
    "GrainBoundary": "core.interface",
    "oxide_type": "core.structure_analyzer",
    "AbstractElectrode": "apps.battery.battery_abc",
    "ConversionElectrode": "apps.battery.conversion_battery",
    "ConversionVoltagePair": "apps.battery.conversion_battery",
    "InsertionElectrode": "apps.battery.insertion_battery",
    "InsertionVoltagePair": "apps.battery.insertion_battery",
    "WAVELENGTHS": "analysis.diffraction.xrd",
    "XRDCalculator": "analysis.diffraction.xrd",
    "QCInput": "io.qchem.inputs",
    "QCOutput": "io.qchem.outputs",
    "CollinearMagneticStructureAnalyzer": "analysis.magnetism",
    "Ordering": "analysis.magnetism.analyzer",
    "BaseVolumetricData": "io.common",
    "bader_analysis_from_path": "command_line.bader_caller",
    "ChargemolAnalysis": "command_line.chargemol_caller",
    "BabelMolAdaptor": "io.babel",
    "ElasticTensor": "analysis.elasticity",
    "ElasticTensorExpansion": "analysis.elasticity",
    "Deformation": "analysis.elasticity.strain",
    "Strain": "analysis.elasticity.strain",
    "Stress": "analysis.elasticity.stress",
    "NearNeighbors": "analysis.local_env",
    "CrystalNN": "analysis.local_env",
    "OpenBabelNN": "analysis.local_env",
    "metal_edge_extender": "analysis.local_env",
    "LocalStructOrderParams": "analysis.local_env",
    "CN_OPT_PARAMS": "analysis.local_env",
    "get_angle": "util.coord",
    "AflowPrototypeMatcher": "analysis.prototypes",
    "weisfeiler_lehman_graph_hash": "util.graph_hashing",
    "get_structure_components": "analysis.dimensionality",
    "Cohp": "electronic_structure.cohp",
    "CompleteCohp": "electronic_structure.cohp",
    "LobsterCompleteDos": "electronic_structure.dos",
    "SimplestChemenvStrategy": "analysis.chemenv.coordination_environments.chemenv_strategies",
    "AllCoordinationGeometries": "analysis.chemenv.coordination_environments.coordination_geometries",
    "LocalGeometryFinder": "analysis.chemenv.coordination_environments.coordination_geometry_finder",
    "LightStructureEnvironments": "analysis.chemenv.coordination_environments.structure_environments",
    "TransformedStructure": "alchemy.materials",
    "Author": "util.provenance",
    "HistoryNode": "util.provenance",
    "StructureNL": "util.provenance",
    "STRUCTURES_DIR": "util.testing",
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
"""Dict of object names to their base import string.

Can be an alias"""

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
