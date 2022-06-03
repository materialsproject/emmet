class MigrationGraphBuilder(MapBuilder):
    def __init__(
        self,
        electrodes: MongoStore,
        tasks: MongoStore,
        target: MongoStore,
        ltol: float = 0.4,
        stol: float = 0.6,
        angle_tol: float = 15,
        **kwargs
    ):
        self.electrodes = electrodes
        self.tasks = tasks
        self.ltol = ltol
        self.stol = stol
        self.angle_tol = angle_tol
        self.target = target
        self.wi_entries = {}
        
        super().__init__(source=electrodes, target=target, **kwargs)
        self.sources.append(tasks)
    
    def get_items(self):
        for item in super(MigrationGraphBuilder,self).get_items():
            tds = list(self.tasks.query({"task_id":{"$in":item["material_ids"]}}))
            item.update({"task_docs":tds})
            yield item
    
    #get structure entry from task store and attach migration graph dict to item
    def unary_function(self, item):
        new_item = dict(item)
        task_documents = [TaskDocument.parse_obj(td) for td in new_item["task_docs"]]
        entries = [task_doc.structure_entry for task_doc in task_documents]
        #get entry is working_ion is new. limit MPRester calls
        if new_item["working_ion"] not in self.wi_entries.keys():
            self.wi_entries[new_item["working_ion"]] = min(compatibility.process_entries(
                mpr.get_entries_in_chemsys([new_item["working_ion"]])), 
                                                           key = lambda x : x.energy_per_atom)
        mg = get_migration_graph(compatibility.process_entries(entries), 
                                 self.wi_entries[new_item["working_ion"]], 
                                 ltol=self.ltol, stol=self.stol, angle_tol=self.angle_tol)
        new_item["mg"] = mg
        return new_item
    
    def get_migration_graph(cses, wi_entry, max_distance_min=0.1, max_distance_max=10, ltol=0.4, stol=0.6, angle_tol=15) -> dict:
        wi = wi_entry.composition.chemical_system
        try:
            mg_structures = MigrationGraph.get_structure_from_entries(entries=cses, migrating_ion_entry=wi_entry, ltol=ltol, stol=stol, angle_tol=angle_tol)
            mg = None
            max_distance = max_distance_min

            if len(mg_structures) > 0:
                while mg == None and max_distance < max_distance_max:
                    mg_trial = MigrationGraph.with_distance(structure=mg_structures[0], migrating_specie=wi, max_distance=max_distance)
                    if mg_trial.m_graph.graph.number_of_edges() > 0:
                        mg_trial.assign_cost_to_graph(['hop_distance'])
                        paths = list(mg_trial.get_path())
                        if len(paths) == 0:
                            max_distance = max_distance*1.1
                        else:
                            mg = mg_trial
                    else:
                        max_distance = max_distance*1.1
                return mg.as_dict()
        except:
            return None
