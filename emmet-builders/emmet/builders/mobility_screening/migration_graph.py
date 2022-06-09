from emmet.core.vasp.task_valid import TaskDocument
from pymatgen.analysis.diffusion.neb.full_path_mapper import MigrationGraph
from pymatgen.entries.computed_entries import ComputedEntry, ComputedStructureEntry
from maggma.stores import MongoStore
from maggma.builders import MapBuilder
from pymatgen.ext.matproj import MPRester
from pymatgen.entries.compatibility import MaterialsProject2020Compatibility


class MigrationGraphBuilder(MapBuilder):
    def __init__(
        self,
        electrodes: MongoStore,
        tasks: MongoStore,
        migration_graphs: MongoStore,
        ltol: float = 0.4,
        stol: float = 0.6,
        angle_tol: float = 15,
        **kwargs
    ):
        """
        Attach corresponding migration graphs to each electrode document by getting its computed structure
            entry from an auxilarry task store.
        Args:
        electrodes (Store): Store of electrode documents that contains task_ids for its materials
        tasks (Store): Store of task documents that contain the structure entry, to be paired with
            each electrode docs based on material ids
        migration_graphs (Store): Target store for electrode docs with attached migration graph
        query (dict): dictionary to limit materials to be analyzed ---
            only applied to the materials when we need to group structures
            the phase diagram is still constructed with the entire set
        ltol: fractional length tolerance for StructureMatcher
        stol: site tolerance for StructureMatcher
        angle_tol: angle tolerance for StructureMatcher
        """
        self.electrodes = electrodes
        self.tasks = tasks
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.migration_graphs = migration_graphs
        self.wi_entries = {}
        self.mpr = MPRester()
        self.compatibility = MaterialsProject2020Compatibility()
        super().__init__(source=electrodes, target=migration_graphs, **kwargs)
        self.sources.append(tasks)

    def get_items(self) -> dict:
        """
        get structure entry from task store
        """
        for item in super(MigrationGraphBuilder, self).get_items():
            tds = list(
                self.tasks.query(
                    {
                        "task_id": {
                            "$in": [
                                i if i[:2] == "js" else int(i)
                                for i in item["material_ids"]
                            ]
                        }
                    }
                )
            )
            item.update({"task_docs": tds})
            yield item

    def unary_function(self, item: dict) -> dict:
        """
        attach migration graph dict to item
        """
        new_item = dict(item)
        task_documents = [TaskDocument.parse_obj(td) for td in new_item["task_docs"]]
        entries = [task_doc.structure_entry for task_doc in task_documents]
        # get entry iff working_ion is new to limit MPRester calls
        if new_item["working_ion"] not in self.wi_entries.keys():
            self.wi_entries[new_item["working_ion"]] = min(
                self.compatibility.process_entries(
                    self.mpr.get_entries_in_chemsys([new_item["working_ion"]])
                ),
                key=lambda x: x.energy_per_atom,
            )
        mg = self.get_migration_graph(
            self.compatibility.process_entries(entries),
            self.wi_entries[new_item["working_ion"]],
            ltol=self.ltol,
            stol=self.stol,
            angle_tol=self.angle_tol,
        )
        new_item["migration_graph"] = mg
        return new_item

    def get_migration_graph(
        self,
        cses: [ComputedStructureEntry],
        wi_entry: [ComputedEntry],
        ltol,
        stol,
        angle_tol,
        max_distance_min=0.1,
        max_distance_max=10,
    ) -> dict:
        wi = wi_entry.composition.chemical_system
        try:
            mg_structures = MigrationGraph.get_structure_from_entries(
                entries=cses,
                migrating_ion_entry=wi_entry,
                ltol=ltol,
                stol=stol,
                angle_tol=angle_tol,
            )
            mg = None
            max_distance = max_distance_min

            if len(mg_structures) > 0:
                while mg == None and max_distance < max_distance_max:
                    mg_trial = MigrationGraph.with_distance(
                        structure=mg_structures[0],
                        migrating_specie=wi,
                        max_distance=max_distance,
                    )
                    if mg_trial.m_graph.graph.number_of_edges() > 0:
                        mg_trial.assign_cost_to_graph(["hop_distance"])
                        paths = list(mg_trial.get_path())
                        if len(paths) == 0:
                            max_distance = max_distance * 1.1
                        else:
                            mg = mg_trial
                    else:
                        max_distance = max_distance * 1.1
                return mg.as_dict()
        except:
            return None
