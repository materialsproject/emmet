import logging
import os
import glob
import hashlib
from datetime import datetime

from pymatgen.core.structure import Structure

from maggma.builder import Builder

__author__ = "Matthew Horton <mkhorton@lbl.gov>"


class FileChecker(Builder):
    def __init__(self, tasks, filechecker, query={}, **kwargs):
        """
        Calculates hashes for files, to alert us if files go missing.

        Args:
            tasks (Store): Store of task data
            filechecker (Store): Store of file integrity
            query (dict): dictionary to limit materials to be analyzed
        """

        self.tasks = tasks
        self.filechecker = filechecker
        self.query = query

        self.__logger = logging.getLogger(__name__)
        self.__logger.addHandler(logging.NullHandler())

        super().__init__(sources=[tasks],
                         targets=[filechecker],
                         **kwargs)

    def get_items(self):

        self.__logger.info("FileChecker Builder Started")

        q = dict(self.query)
        tasks = self.tasks().find(q, {'task_id': 1,
                                      'dir_name': 1})

        return tasks

    def process_item(self, item):
        self.__logger.debug("Calculating hashes for {}".format(item['task_id']))

        root_dir = item['dir_name']

        current_hash_doc = self.filechecker().find({'task_id': item['task_id']})
        hash_doc = {'status': None}

        # remove hostname if it's present, assumes builder runs on same host
        # or has access to the root_dir
        root_dir = root_dir.split(':')[1] if ':' in root_dir else root_dir

        # sanity check, won't catch all cases though...
        test_dir = root_dir.split('/')[0]
        if not os.path.isdir(test_dir):
            self.__logger.error("Cannot access {} for task {}, "
                                "is builder running on correct host?".format(test_dir, item))
        else:
            if not os.path.isdir(root_dir):
                hash_doc.update(current_hash_doc)
                hash_doc['status'] = "Directory not found"
            else:
                files = glob.glob(root_dir+"/*")
                for f in files:
                    hasher = hashlib.sha256()
                    with open(f, 'rb') as file_to_hash:
                        buffer = file_to_hash.read()
                        hasher.update(buffer)
                    hash_doc['files'][f] = str(hasher.hexdigest())

        if hash_doc['files'] != current_hash_doc['files']:

            self.__logger.error("Possibly corrupted files in {} for task_id {}"
                                .format(root_dir, item['task_id']))

            hash_doc['status'] = "Possible corrupted files"
            hash_doc['old_hash_doc'] = current_hash_doc

        return hash_doc

    def update_targets(self, items):

        self.__logger.info("Updating {} diffraction documents".format(len(items)))

        for doc in items:
            doc[self.filechecker.lu_field] = datetime.utcnow()
            self.filechecker().replace_one({"task_id": doc['task_id']}, doc, upsert=True)
