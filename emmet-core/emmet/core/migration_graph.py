from typing import Dict, List, Union, Tuple

from pydantic import BaseModel, Field, validator
from pymatgen.analysis.diffusion.neb.full_path_mapper import MigrationGraph
from pymatgen.analysis.diffusion.neb.pathfinder import MigrationHop
from pymatgen.analysis.graphs import StructureGraph
from pymatgen.core import Composition, Structure, PeriodicSite


class Hop(BaseModel):
    """
    Data for a particular hop, this is distinct from the Migration Hop object since this document
    only stores the data related a particualr hop but not the symmetrized structure itself.
    """
    iindex: int = Field(None, description="")
    eindex: int = Field(None, description="")
    ipos: Tuple[float, float, float] = Field(None, description="")
    epos: Tuple[float, float, float] = Field(None, description="")
    ipos_cart: Tuple[float, float, float] = Field(None, description="")
    epos_cart: Tuple[float, float, float] = Field(None, description="")
    to_jimage: Tuple[int, int, int] = Field(None, description="")
    distance: float = Field(None, description="")
    hop_label: int = Field(None, description="")


class MigrationGraphDoc(BaseModel):
    """
    Data for MigrationGraph objects from pymatgen-diffusion.
    Note:
        This will just be used to construct the object for each material.
        The only data we will use are the "site energies" defined at each meta-stable migrating ion site.
        In the future more advanced query capabilities should be introduced with fields in the document model.
    """

    structure: Structure = Field(
        None,
        description="The atomic structure with all migting ion sites represented as atoms of the same species."
    )

    m_graph: StructureGraph = Field(
        None,
        description="The structure graph that represents the migration network."
    )

    hops: Dict[int, Hop] = Field(
        None,
        description="All of the hops in the system given as a list."
    )

    unique_hops: Dict[int, Hop] = Field(
        None,
        description="The unique hops dictionary keyed by the hop label {0: {=Dictionary of properties=}}"
    )

    host_structure: Structure = Field(
        None,
        description="The empty host lattice without the migrating ion."
    )

    symprec: float = Field(None, description="Parameter used by pymatgen to determin equivalent hops.")

    vac_mode: bool = Field(None, description="Indicates whether vacancy mode should be used [currently under-supported].")

    @classmethod
    def from_migration_graph(cls, migration_graph: MigrationGraph):
        """
        Construct the document using a MigrationGraph object
        """
        summary_dict = migration_graph.get_summary_dict()

        return cls(
            structure=migration_graph.structure,
            m_graph=migration_graph.m_graph,
            hops = summary_dict["hops"],
            unique_hops=summary_dict["unique_hops"],
            host_structure=migration_graph.host_structure,
            symprec=migration_graph.symprec,
            vac_mode=migration_graph.vac_mode
        )

    def as_migration_graph(self):
        """
        Get a migration graph object from this document
        """
        mg = MigrationGraph(
            structure=self.structure,
            m_graph=self.m_graph,
            symprec=self.symprec,
            vac_mode=self.vac_mode
        )

        # make sure there is a one-to-one mapping between the unique hops dictionary
        def get_mg_uhop_key(ipos, epos):
            isite = PeriodicSite(coords=self.ipos, lattice=self.structure.lattice)
            esite = PeriodicSite(coords=self.epos, lattice=self.structure.lattice)
            hop = MigrationHop(isite, esite, symm_structure=mg.symm_structure)

            for k,v in mg.unique_hops.items():
                if hop == v['hop']:
                    return k

        for k, v in self.unique_hops.items():
            mg_k = get_mg_uhop_key(v["ipos"], v["epos"])
            if k != mg_k:
                raise RuntimeError("The unique hops in the reconstructed migration graph is different than the one "
                                   f"in the document MigrationGraphDoc ({k}) MigrationGraph ({mg_k})")

        # TODO add any datamapping from the DB to reconstructed object here.

        return mg