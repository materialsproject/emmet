from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import Any

_class_map: dict[str, str] = {
    "__version__": "pymatgen.core",
    "Element": "pymatgen.core.periodic_table",
    "Composition": "pymatgen.core.composition",
    "formula_double_format": "pymatgen.util.string",
    "htmlify": "pymatgen.util.string",
    "latexify": "pymatgen.util.string",
    "latexify_spacegroup": "pymatgen.util.string",
    "unicodeify": "pymatgen.util.string",
    "Lattice": "pymatgen.core.lattice",
    "Specie": "pymatgen.core.periodic_table",
    "Species": "pymatgen.core.periodic_table",
    "DummySpecies": "pymatgen.core.periodic_table",
    "get_el_sp": "pymatgen.core.periodic_table",
    "PeriodicSite": "pymatgen.core.sites",
    "IStructure": "pymatgen.core.structure",
    "Structure": "pymatgen.core.structure",
    "StructureGraph": "pymatgen.core.graphs",
    "Molecule": "pymatgen.core.structure",
    "MoleculeGraph": "pymatgen.core.graphs",
    "BVAnalyzer": "pymatgen.analysis.bond_valence",
    "StructureMatcher": "pymatgen.analysis.structure_matcher",
    "ElementComparator": "pymatgen.analysis.structure_matcher",
    "AbstractComparator": "pymatgen.analysis.structure_matcher",
    "DeformStructureTransformation": "pymatgen.transformations.standard_transformations",
    "MoleculeMatcher": "pymatgen.analysis.molecule_matcher",
    "Trajectory": "pymatgen.core.trajectory",
    "SpacegroupAnalyzer": "pymatgen.symmetry.analyzer",
    "PointGroupAnalyzer": "pymatgen.symmetry.analyzer",
    "SymmetryUndeterminedError": "pymatgen.symmetry.analyzer",
    "EOS": "pymatgen.analysis.eos",
    "EOSError": "pymatgen.analysis.eos",
    "PiezoTensor": "pymatgen.analysis.piezo",
    "Tensor": "pymatgen.core.tensors",
    "TensorMapping": "pymatgen.core.tensors",
    "SYMM_DATA": "pymatgen.symmetry.groups",
    "CifBlock": "pymatgen.io.cif",
    "CifParser": "pymatgen.io.cif",
    "HighSymmKpath": "pymatgen.symmetry.bandstructure",
    "Kpoint": "pymatgen.electronic_structure.bandstructure",
    "BandStructure": "pymatgen.electronic_structure.bandstructure",
    "BandStructureSymmLine": "pymatgen.electronic_structure.bandstructure",
    "Dos": "pymatgen.electronic_structure.dos",
    "CompleteDos": "pymatgen.electronic_structure.dos",
    "Spin": "pymatgen.electronic_structure.core",
    "Orbital": "pymatgen.electronic_structure.core",
    "OrbitalType": "pymatgen.electronic_structure.core",
    "PhononBandStructureSymmLine": "pymatgen.phonon.bandstructure",
    "PhononDos": "pymatgen.phonon.dos",
    "CompletePhononDos": "pymatgen.phonon.dos",
    "XAS": "pymatgen.analysis.xas.spectrum",
    "site_weighted_spectrum": "pymatgen.analysis.xas.spectrum",
    "PhaseDiagram": "pymatgen.analysis.phase_diagram",
    "IRDielectricTensor": "pymatgen.phonon.ir_spectra",
    "ComputedEntry": "pymatgen.core.entries",
    "ComputedStructureEntry": "pymatgen.core.entries",
    "Compatibility": "pymatgen.analysis.compatibility",
    "MaterialsProject2020Compatibility": "pymatgen.analysis.compatibility",
    "MaterialsProjectAqueousCompatibility": "pymatgen.analysis.compatibility",
    "Incar": "pymatgen.io.vasp.inputs",
    "Kpoints": "pymatgen.io.vasp.inputs",
    "Poscar": "pymatgen.io.vasp.inputs",
    "PotcarSingle": "pymatgen.io.vasp",
    "Potcar": "pymatgen.io.vasp.inputs",
    "Vasprun": "pymatgen.io.vasp.outputs",
    "BSVasprun": "pymatgen.io.vasp.outputs",
    "Locpot": "pymatgen.io.vasp.outputs",
    "Oszicar": "pymatgen.io.vasp.outputs",
    "Outcar": "pymatgen.io.vasp.outputs",
    "VolumetricData": "pymatgen.io.vasp.outputs",
    "Chgcar": "pymatgen.io.vasp.outputs",
    "VaspInputSet": "pymatgen.io.vasp.sets",
    "MPStaticSet": "pymatgen.io.vasp.sets",
    "BalancedReaction": "pymatgen.analysis.reaction_calculator",
    "DiffractionPattern": "pymatgen.analysis.diffraction.xrd",
    "MaterialsProjectDFTMixingScheme": "pymatgen.entries.mixing_scheme",
    "GrainBoundary": "pymatgen.core.interface",
    "oxide_type": "pymatgen.core.structure_analyzer",
    "AbstractElectrode": "pymatgen.apps.battery.battery_abc",
    "ConversionElectrode": "pymatgen.apps.battery.conversion_battery",
    "ConversionVoltagePair": "pymatgen.apps.battery.conversion_battery",
    "InsertionElectrode": "pymatgen.apps.battery.insertion_battery",
    "InsertionVoltagePair": "pymatgen.apps.battery.insertion_battery",
    "WAVELENGTHS": "pymatgen.analysis.diffraction.xrd",
    "XRDCalculator": "pymatgen.analysis.diffraction.xrd",
    "QCInput": "pymatgen.io.qchem.inputs",
    "QCOutput": "pymatgen.io.qchem.outputs",
    "CollinearMagneticStructureAnalyzer": "pymatgen.analysis.magnetism",
    "Ordering": "pymatgen.analysis.magnetism",
    "BaseVolumetricData": "pymatgen.io.common",
    "bader_analysis_from_path": "pymatgen.command_line.bader_caller",
    "ChargemolAnalysis": "pymatgen.command_line.chargemol_caller",
    "BabelMolAdaptor": "pymatgen.io.babel",
    "ElasticTensor": "pymatgen.analysis.elasticity",
    "ElasticTensorExpansion": "pymatgen.analysis.elasticity",
    "Deformation": "pymatgen.analysis.elasticity.strain",
    "Strain": "pymatgen.analysis.elasticity.strain",
    "Stress": "pymatgen.analysis.elasticity.stress",
    "NearNeighbors": "pymatgen.analysis.local_env",
    "CrystalNN": "pymatgen.analysis.local_env",
    "OpenBabelNN": "pymatgen.analysis.local_env",
    "metal_edge_extender": "pymatgen.analysis.local_env",
    "LocalStructOrderParams": "pymatgen.analysis.local_env",
    "CN_OPT_PARAMS": "pymatgen.analysis.local_env",
    "get_angle": "pymatgen.util.coord",
    "AflowPrototypeMatcher": "pymatgen.analysis.prototypes",
    "weisfeiler_lehman_graph_hash": "pymatgen.util.graph_hashing",
    "get_structure_components": "pymatgen.analysis.dimensionality",
    "Cohp": "pymatgen.electronic_structure.cohp",
    "CompleteCohp": "pymatgen.electronic_structure.cohp",
    "LobsterCompleteDos": "pymatgen.electronic_structure.dos",
    "SimplestChemenvStrategy": "pymatgen.analysis.chemenv.coordination_environments.chemenv_strategies",
    "AllCoordinationGeometries": "pymatgen.analysis.chemenv.coordination_environments.coordination_geometries",
    "LocalGeometryFinder": "pymatgen.analysis.chemenv.coordination_environments.coordination_geometry_finder",
    "LightStructureEnvironments": "pymatgen.analysis.chemenv.coordination_environments.structure_environments",
    "TransformedStructure": "pymatgen.alchemy.materials",
    "Author": "pymatgen.util.provenance",
    "HistoryNode": "pymatgen.util.provenance",
    "StructureNL": "pymatgen.util.provenance",
    "STRUCTURES_DIR": "pymatgen.util.testing",
    # pymatgen-analysis-alloys add-on
    "AlloyMember": "pymatgen.analysis.alloys.core",
    "AlloyPair": "pymatgen.analysis.alloys.core",
    "AlloySystem": "pymatgen.analysis.alloys.core",
    # pymatgen-analysis-diffusion add-on
    "MigrationGraph": "pymatgen.analysis.diffusion.neb.full_path_mapper",
    "add_edge_data_from_sc": "pymatgen.analysis.diffusion.utils.edge_data_from_sc",
    "get_sc_fromstruct": "pymatgen.analysis.diffusion.utils.supercells",
    "get_start_end_structures": "pymatgen.analysis.diffusion.utils.supercells",
    # pymatgen-io-validation add-on
    "REQUIRED_VASP_FILES": "pymatgen.io.validation.validation",
    "VaspValidator": "pymatgen.io.validation.validation",
    "LightOutcar": "pymatgen.io.validation.common",
    "LightVasprun": "pymatgen.io.validation.common",
    "PotcarSummaryStats": "pymatgen.io.validation.common",
    "VaspFiles": "pymatgen.io.validation.common",
    "VaspInputSafe": "pymatgen.io.validation.common",
    # pymatgen-analysis-defects add-on
    "Defect": "pymatgen.analysis.defects.core",
    # pymatgen-io-lobster add-on
    "Bandoverlaps": "pymatgen.io.lobster",
    "Charge": "pymatgen.io.lobster",
    "Doscar": "pymatgen.io.lobster",
    "Grosspop": "pymatgen.io.lobster",
    "Icohplist": "pymatgen.io.lobster",
    "Lobsterin": "pymatgen.io.lobster",
    "Lobsterout": "pymatgen.io.lobster",
    "MadelungEnergies": "pymatgen.io.lobster",
    "SitePotential": "pymatgen.io.lobster",
}
"""Dict of object names to their base import string.

Can be an alias"""

_name_collision_aliases: dict[str, str] = {"BaseVolumetricData": "VolumetricData"}
"""Aliases for classes to avoid name collisions."""


def __getattr__(name: str) -> Any:
    """Lazily load and cache objects from pymatgen."""
    if name in _class_map:
        return getattr(
            import_module(_class_map[name]), _name_collision_aliases.get(name, name)
        )
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> Sequence[str]:
    return sorted(
        ".".join((base_import, _name_collision_aliases.get(name, name)))
        for name, base_import in _class_map.items()
    )
