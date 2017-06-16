from maggma.builder import Builder

__author__ = "Shyam Dwaraknath"
__email__ = "shyamd@lbl.gov"

class TaskTagger(Builder):
    def __init__(self, tasks, task_types, **kwargs):
        """
        Creates task_types from tasks and type definitions

        Args:
            tasks (Store): Store of task documents
            task_defs (Store): Store of task_definitions. These define 
            task_types (Store): Store of task_types for tasks
        """
        self.tasks = tasks
        self.task_types = task_types

        super().__init__(sources=[tasks],
                         targets=[task_types],
                         **kwargs)

    def get_items(self):
        """
        Returns all task docs and tag definitions to process

        Returns:
            generator or list of task docs and tag definitions
        """

        # Get all tasks ids from the tasks collection
        all_task_ids = self.tasks.collection.distinct("task_id", {"state": "successful"})

        
        # Figure out which task_ids are not in the materials collection and only process those
        previous_task_ids = self.task_types.collection.distinct("task_id", {"task_type": {"$exists": 0}})
        to_process = set(all_task_ids) - set(previous_task_ids)

        # Process each task_id
        for t_id in to_process:
            print("Processing task_id: {}".format(t_id))
            try:
                yield self.tasks.collection.find_one({"task_id": t_id})
            except:
                import traceback
                print("Problem processing task_id: {}".format(t_id))

    def process_item(self, item):
        """
        Find the task_type for the item 
        
        Args:
            item ((dict,[dict])): a task doc and a list of possible tag definitions
        """

        return {"task_id": item["task_id"],
                "task_type": self.task_type(item)}

    def update_targets(self, items):
        """
        Inserts the new task_types into the task_types collection
        
        Args:
            items ([dict]): task_type dicts to insert into task_types collection
        """
        for doc in items:
            self.task_types.collection.update({'task_id': doc['task_id']}, doc, upsert=True)

    def finalize(self):
        pass

    def task_type(self, task_doc):
        """
        Determines the task_type

        Args:
            task_doc (dict): task_document with original input
        """
        incar = task_doc["input_orig"]["INCAR"]

        if incar.get("LHFCALC",False):
            if incar.get("NSW") == 0:
                return "hse bs"
            else:
                return "hse"

        if incar.get("ICHARG",0) > 10:
            if incar.get("NEDOS",0) > 600:
                return "nscf uniform"
            else:
                return "nscf line"


        if incar.get("LEPSILON",False):
            return "static dielectric"


        if incar.get("IBRION",0) < 0:
            return "static"


        if incar.get("ISIF",2) == 3 and incar.get("IBRION",0) > 0:
            return "structure optimization"

        return ""