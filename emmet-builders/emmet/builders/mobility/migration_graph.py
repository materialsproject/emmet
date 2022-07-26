from maggma.builders.map_builder import MapBuilder
from maggma.stores import MongoStore
from emmet.core.mobility.migrationgraph import MigrationGraphDoc
from emmet.builders.utils import get_hop_cutoff
from pymatgen.apps.battery.insertion_battery import InsertionElectrode
from pymatgen.analysis.diffusion.neb.full_path_mapper import MigrationGraph
from emmet.core.utils import jsanitize


class MigrationGraphBuilder(MapBuilder):
    def __init__(
        self,
        insertion_electrode: MongoStore,
        migration_graph: MongoStore,
        algorithm: str = "hops_based",
        min_hop_distance: float = 1,
        max_hop_distance: float = 7,
        **kwargs,
    ):
        self.insertion_electode = insertion_electrode
        self.migration_graph = migration_graph
        self.algorithm = algorithm
        self.min_hop_distance = min_hop_distance
        self.max_hop_distance = max_hop_distance
        super().__init__(source=insertion_electrode, target=migration_graph, **kwargs)
        self.connect()

    def unary_function(self, item):
        # get entries and info from insertion electrode
        ie = InsertionElectrode.from_dict(item["electrode_object"])
        entries = ie.get_all_entries()
        wi_entry = ie.working_ion_entry

        # get migration graph structure
        struct = MigrationGraph.get_structure_from_entries(entries, wi_entry)
        if type(struct) == list:
            if len(struct) > 1:
                self.logger.warn(
                    f"migration graph ambiguous: {len(struct)} possible options"
                )
            struct = struct[0]

        # get hop cutoff distance
        d = get_hop_cutoff(
            migration_graph_struct=struct,
            mobile_specie=wi_entry.composition.chemical_system,
            algorithm=self.algorithm,
            min_hop_distance=self.min_hop_distance,
            max_hop_distance=self.max_hop_distance,
        )

        # get migration graph
        mg_doc = MigrationGraphDoc.from_entries_and_distance(
            battery_id=item["battery_id"],
            grouped_entries=entries,
            working_ion_entry=wi_entry,
            hop_cutoff=d,
        )

        return jsanitize(mg_doc.dict())
