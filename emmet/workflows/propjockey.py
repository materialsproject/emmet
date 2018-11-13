"""
This module is intended to allow building derivative workflows
for material properties based on missing properties in a
materials collection
"""

import logging
import tqdm

from maggma.builders import Builder
from maggma.stores import MongoStore
from fireworks import LaunchPad
from datetime import datetime

logger = logging.getLogger(__name__)

__author__ = "Joseph Montoya"
__maintainer__ = "Joseph Montoya"
__email__ = "montoyjh@lbl.gov"


# TODO: this could be abstracted to allow for multiple kinds of workflows
# TODO: maybe input should be a fws store instead of an lpad
# TODO: incremental building doesn't currently work, but needs to be,
#       fixed on the propjockey side
class ElasticPropjockeyPrioritizer(Builder):
    def __init__(self, pj_store, lpad, incremental=True,
                 query=None, base_priority=2500, site_penalty=10,
                 vote_weight=10, **kwargs):
        """
        Takes a propjockey collection and sets the priority
        of a fireworks in a fireworks collection from a LaunchPad

        Args:
            pj_store (Store): store corresponding to propjockey collection
            lpad (LaunchPad): fireworks launchpad
            query (dict): query to filter the propjockey store
            base_priority (int): base priority to assign to fireworks
            site_penalty (int): per-site penalty to priority
            vote_weight (int): priority boost per vote
            **kwargs (kwargs): kwargs for builder
        """
        self.pj_store = pj_store
        if isinstance(lpad, dict):
            self.lpad = LaunchPad.from_dict(lpad)
        else:
            self.lpad = lpad
        self.fws_store = MongoStore.from_collection(self.lpad.fireworks)
        self.fws_store.lu_field = "_pj_lu"
        self.incremental = incremental
        self.start_date = datetime.utcnow()
        self.query = query or {}
        self.base_priority = base_priority
        self.site_penalty = site_penalty
        self.vote_weight = vote_weight

        super().__init__(sources=[self.pj_store],
                         targets=[self.fws_store], **kwargs)

    def get_items(self):
        """
        Gets all propjockey and fireworks docs to process

        Returns:
             generator for items
        """
        if self.incremental:
            self.logger.info("Ensuring indices on lu_field for sources/targets")
            self.pj_store.ensure_index(self.pj_store.lu_field)
            self.fws_store.ensure_index(self.fws_store.lu_field)
            pj_filter = self.query.copy()
            pj_filter.update(self.pj_store.lu_filter(self.fws_store))
        else:
            pj_filter = self.query

        pj_filter.update({"state": {"$ne": "COMPLETED"}})
        pj_cursor = self.pj_store.query(['nrequesters', 'material_id'],
                                        pj_filter)
        self.total = pj_cursor.count()
        self.fws_store.ensure_index("spec.tags")
        self.fws_store.ensure_index("name")
        for doc in pj_cursor:
            logger.debug("Processing {}".format(doc["material_id"]))
            fw = self.fws_store.query_one(
                criteria={"spec.tags": doc['material_id'],
                          "name": {"$regex": "structure optimization"}})
            if not fw:
                logger.info("No fw found for {}".format(doc['material_id']))
            else:
                yield doc, fw

    def process_item(self, item):
        """
        Processes items into workflows

        Args:
            item ((dict, list)): pair of doc and task_ids to filter

        Returns:
            Workflow
        """
        doc, fw = item
        nsites = len(fw['spec']['_tasks'][1]['structure']['sites'])
        priority = self.base_priority - nsites * self.site_penalty + \
            self.vote_weight * doc['nrequesters']
        return (doc['material_id'], priority)

    def update_targets(self, items):
        """
        Filters items and updates the launchpad

        Args:
            items ([Workflow]): list of workflows to be added
        """
        for material_id, priority in tqdm.tqdm(items, desc="updating fws"):
            self.fws_store.collection.update_many(
                {"spec.tags": material_id, "spec.elastic_category": "minimal"},
                {"$set": {"spec._priority": priority,
                          "spec._pj_lu": self.start_date}})
