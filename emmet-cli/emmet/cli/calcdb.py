# coding: utf-8
"""
This modules defines a base class of a calculation database
"""

import regex
import logging

from datetime import datetime
from typing import Dict, List, Union, Tuple
from abc import ABCMeta, abstractmethod
from pydash.objects import has, get, unset

from monty.json import MSONable
from monty.serialization import loadfn
from maggma.stores import Store, MongoStore

from emmet.core.utils import jsanitize

logger = logging.getLogger("emmet")


class CalcDB(MSONable, metaclass=ABCMeta):
    def __init__(
        self,
        documents: MongoStore,
        data: Store,
        key_regex: Tuple[str, str] = ("mp-{id}", r"mp-(\d*)|0$"),
        doc_keys: Dict[str, str] = {
            "bandstructure": "calcs_reversed.0.bandstructure",
            "dos": "calcs_reversed.0.dos",
        },
        removed_keys: List[str] = [
            "calcs_reversed.1.bandstructure",
            "calcs_reversed.2.bandstructure",
            "calcs_reversed.1.dos",
            "calcs_reversed.2.dos",
        ],
    ):

        self.documents = documents
        self.data = data
        self.key_regex = key_regex
        self.doc_keys = doc_keys
        self.removed_keys = removed_keys

        self._key_name = self.documents.key

    def build_indexes(self, indexes=None, background=True):
        """
         Build the indexes.
         Args:
             indexes (list): list of single field indexes to be built.
             background (bool): Run in the background or not.
         """
        self.documents.connect()
        self.data.connect()

        self.documents.ensure_index("task_id")
        self.documents.ensure_index("last_updated")
        self.documents.ensure_index("dir_name")

        self.documents.ensure_index("task_id")
        self.documents.ensure_index("last_updated")
        self.documents.ensure_index("type")

    def insert(self, tasks: Union[Dict, List[Dict]], update_duplicates=True):
        """
        Insert the task documents to the documents store
        Args:
            d (dict): task document
            update_duplicates (bool): whether to update the duplicates
        """

        self.documents.connect()
        self.data.connect()
        self.build_indexes()

        tasks = [tasks] if isinstance(tasks, Dict) else tasks

        result = {
            d["dir_name"]: d[self._key_name]
            for d in self.documents.query(
                {"dir_name": {"$in": [d["dir_name"] for d in tasks]}},
                ["dir_name", self._key_name],
            )
        }

        to_update = []
        for doc in tasks:
            doc["last_updated"] = datetime.utcnow()
            if doc["dir_name"] not in result and "task_id" not in doc:
                to_update.append(jsanitize(doc, allow_bson=True))
            elif update_duplicates:
                doc["task_id"] = result["task_id"]
                logger.info(
                    "Updating {} with taskid = {}".format(d["dir_name"], d["task_id"])
                )
                to_update.append(jsanitize(doc, allow_bson=True))

        all_task_ids = self.documents.distinct("task_id")
        all_task_ids = {
            self.key_regex[1].search(tid).group() for tid in all_task_ids
        } - {
            0,
        }  # Remove task_id 0

        sep_tid = max(all_task_ids) + len(to_update)
        next_tid = max(all_task_ids) + 1
        self.documents.update({"task_id": sep_tid}, key="task_id")
        logger.debug(f"Inserted separator task with task_id {sep_tid}.")

        all_task_ids = self.documents.distinct("task_id")
        all_task_ids = {
            self.key_regex[1].search(tid).group() for tid in all_task_ids
        } - {
            0,
        }  # Remove task_id 0

        assert (
            max(all_task_ids) == sep_tid
        ), f"Failed reserving block of {len(to_update)} task_ids"
        for d in to_update:
            if "task_id" not in d:
                d["task_id"] = self.key_regex[0].format(next_tid)
                next_tid += 1

        data = self.extract_data(to_update)
        self.documents.update(to_update, key="task_id")
        self.data.update(data, key=("task_id", "type"))

    def extract_data(self, docs) -> List[Dict]:
        """
        Extracts the data blobs in-place, removing them from the provided documents
        """

        data = []

        for d in docs:
            for doc_type, path in self.doc_keys.items():
                if has(d, path):
                    new_blob = get(d, path)
                    new_blob["type"] = doc_type
                    new_blob["task_id"] = d["task_id"]
                    new_blob["last_updated"] = d["last_updated"]
                    data.append(new_blob)
                    unset(d, path)
            for path in self.removed_keys:
                unset(d, path)
        return data
