# test_utils/async_mongomock.py
from typing import Any, Dict, List
import mongomock
from pymongo import ReturnDocument


class AsyncMongomockCursor:
    """Wrapper to make mongomock cursor async-compatible"""

    def __init__(self, cursor):
        self.cursor = cursor

    async def to_list(self, length=None):
        return list(self.cursor)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self.cursor)
        except StopIteration:
            raise StopAsyncIteration


class AsyncMongomockCollection:
    """Wrapper to make mongomock collection async-compatible"""

    def __init__(self, collection):
        self.collection = collection
        self.name = collection.name

    async def find_one(self, filter=None, *args, **kwargs):
        return self.collection.find_one(filter, *args, **kwargs)

    def find(self, filter=None, *args, **kwargs):
        cursor = self.collection.find(filter, *args, **kwargs)
        return AsyncMongomockCursor(cursor)

    async def insert_one(self, document):
        return self.collection.insert_one(document)

    async def insert_many(self, documents):
        return self.collection.insert_many(documents)

    async def update_one(self, filter, update, upsert=False):
        return self.collection.update_one(filter, update, upsert=upsert)

    async def update_many(self, filter, update, upsert=False):
        return self.collection.update_many(filter, update, upsert=upsert)

    async def delete_one(self, filter):
        return self.collection.delete_one(filter)

    async def delete_many(self, filter):
        return self.collection.delete_many(filter)

    async def count_documents(self, filter=None, **kwargs):
        # Filter out unsupported kwargs like 'hint'
        filtered_kwargs = {
            k: v for k, v in kwargs.items() if k not in ["hint", "maxTimeMS"]
        }
        return self.collection.count_documents(filter or {}, **filtered_kwargs)

    async def find_one_and_update(
        self,
        filter,
        update,
        return_document=ReturnDocument.AFTER,
        upsert=False,
        **kwargs
    ):
        return self.collection.find_one_and_update(
            filter, update, return_document=return_document, upsert=upsert, **kwargs
        )

    async def find_one_and_delete(self, filter):
        return self.collection.find_one_and_delete(filter)

    async def aggregate(self, pipeline: List[Dict[str, Any]], **kwargs):
        # Filter out async-specific kwargs that mongomock doesn't support
        filtered_kwargs = {k: v for k, v in kwargs.items() if k not in ["maxTimeMS"]}
        cursor = self.collection.aggregate(pipeline, **filtered_kwargs)
        return AsyncMongomockCursor(cursor)

    async def create_index(self, keys, **kwargs):
        return self.collection.create_index(keys, **kwargs)

    async def drop(self):
        return self.collection.drop()


class AsyncMongomockDatabase:
    """Wrapper to make mongomock database async-compatible"""

    def __init__(self, database):
        self.database = database
        self.name = database.name

    def __getitem__(self, name):
        return AsyncMongomockCollection(self.database[name])

    def get_collection(self, name):
        return AsyncMongomockCollection(self.database[name])

    async def list_collection_names(self):
        return self.database.list_collection_names()

    async def drop_collection(self, name_or_collection):
        return self.database.drop_collection(name_or_collection)


class AsyncMongomockClient:
    """Wrapper to make mongomock client async-compatible"""

    def __init__(self, *args, **kwargs):
        self.client = mongomock.MongoClient(*args, **kwargs)

    def __getitem__(self, name):
        return AsyncMongomockDatabase(self.client[name])

    def get_database(self, name):
        return AsyncMongomockDatabase(self.client[name])

    async def close(self):
        # mongomock doesn't need actual closing
        pass

    async def server_info(self):
        return {"version": "4.4.0", "mongomock": True}
