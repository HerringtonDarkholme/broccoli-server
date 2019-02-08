import json
import pymongo
from typing import Dict, List, Tuple, Optional


class Store(object):
    def __init__(self):
        self.config_cached = False
        self.q = {}
        self.fields = []

        # todo: abstract it out
        # todo: properly close all resources
        self.client = pymongo.MongoClient('localhost', 27017)
        self.db = self.client['broccoli']
        self.collection = self.db['broccoli.api']

    def get_config(self) -> Optional[Tuple[Dict, List[str]]]:
        if self.config_cached:
            return self.q, self.fields
        document = self.collection.find_one(
            {
                "endpoint": "default"
            }
        )
        if not document:
            return None
        q, fields = json.loads(document["q"]), document["fields"]
        self.q, self.fields, self.config_cached = q, fields, True
        return q, fields

    def set_config(self, q: Dict, fields: List[str]):
        self.collection.update_one(
            {
                "endpoint": "default"
            },
            {
                "$set": {
                    "endpoint": "default",
                    "q": json.dumps(q),
                    "fields": fields
                }
            },
            upsert=True
        )
        self.q, self.fields, self.config_cached = q, fields, True
