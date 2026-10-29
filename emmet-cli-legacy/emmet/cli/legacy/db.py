import json
import logging

import pymongo
from pymongo import ReturnDocument

from emmet.core.utils import jsanitize, utcnow


class StorageGateway:
    def __init__(
        self,
        host: str,
        database: str,
        collection: str,
        username: str,
        password: str,
        authSource: str = None,
        protocol: str = "mongodb",
        object_store_auth={},
    ) -> None:
        mongo_uri = f"{protocol}://{username}:{password}@{host}"
        self.client = pymongo.MongoClient(mongo_uri, authSource=authSource or database)
        self.db = self.client[database]
        self._coll = self.db[collection]

        self.object_store_auth = object_store_auth

        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)

        self.logger = logging.getLogger("StorageGateway")
        self.logger.setLevel(logging.INFO)
        self.logger.addHandler(handler)

    @classmethod
    def from_db_file(cls, db_file):
        with open(db_file, "r") as f:
            store_kwargs = json.load(f)

        return cls(**store_kwargs)

    def insert(self, dct: dict, update_duplicates: bool = True) -> str | None:
        result = self._coll.find_one(
            {"dir_name": dct["dir_name"]}, ["dir_name", "task_id"]
        )
        if result is None or update_duplicates:
            dct["last_updated"] = utcnow()
            if result is None:
                self.logger.info("No duplicate!")

                if ("task_id" not in dct) or (not dct["task_id"]):
                    dct["task_id"] = self._coll.find_one_and_update(
                        {"_id": "taskid"},
                        {"$inc": {"c": 1}},
                        return_document=ReturnDocument.AFTER,
                    )["c"]
                self.logger.info(
                    f"Inserting {dct['dir_name']} with taskid = {dct['task_id']}"
                )
            elif update_duplicates:
                dct["task_id"] = result["task_id"]
                self.logger.info(
                    f"Updating {dct['dir_name']} with taskid = {dct['task_id']}"
                )
            dct = jsanitize(dct, allow_bson=True)
            self._coll.update_one(
                {"dir_name": dct["dir_name"]}, {"$set": dct}, upsert=True
            )
            return dct["task_id"]

        else:
            self.logger.info(f"Skipping duplicate {dct['dir_name']}")
