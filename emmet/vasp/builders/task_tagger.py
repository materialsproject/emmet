from maggma.builder import Builder


class TaskTagger(Builder):
    def __init__(self, tasks ,tag_defs, tags, **kwargs):
        """
        Initialize the builder the framework.

        Args:
            tasks (Store): Store of task documents
            tag_defs (Store): Store of tag_definitions
            tags (Store): Store of tags for tasks
        """
        self.tasks = tasks
        self.tags = tags
        self.tag_defs = tag_defs

        super().__init__(sources=[tasks,tag_defs],
                         targets=[tags],
                         **kwargs)


    def get_items(self):
        """
        Returns all the items to process.

        Returns:
            generator or list of items to process
        """

        all_task_ids = self.tasks.distinct("task_id", {"state": "successful"})

        # If there is a new task type definition, re-process the whole collection
        if self.tag_defs.last_updated() > self.tags.last_updated():
            to_process = set(all_task_ids)
        else:
            previous_task_ids = self.tags.distinct("task_id")
            to_process = set(all_task_ids) - set(previous_task_ids)

        tag_defs = list(self.tag_defs.find())

        for t_id in to_process:
            print("Processing task_id: {}".format(t_id))
            try:
                yield {"task_doc": self.tasks.find_one({"task_id":t_id}),
                       "tag_defs": tag_defs}
            except:
                import traceback
                print("Problem processing task_id: {}".format(t_id))

    def process_item(self, item):

        task_doc = item["task_doc"]
        tag_defs = item["tag_defs"]

        for tag_def in tag_defs:
            if self.task_matches_def(task_doc,tag_def):
                return {"task_id": task_doc["task_id"],
                        "task_type": tag_def["task_type"]}
            else
                pass
        pass


    def update_targets(self, items):

        for doc in items:
            self.tags.collection.update({'task_id': doc['task_id']},doc,upsert=True)


    def finalize(self):
        pass


    # TODO: Add in more sophisticated matching criteria
    def task_matches_def(self,task_doc,tag_def):
        for k,v in tag_def['EXACT'].items():
            if task_doc['input_orig']['INCAR'].get(k) is not v:
                return False

        for k,v in tag_def['GREATER'].items():
            if task_doc['input_orig']['INCAR'].get(k,0) < v:
                return False

        for k,v in tag_def['LESS'].items():
            if task_doc['input_orig']['INCAR'].get(k,0) > v:
                return False

        return True