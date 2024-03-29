import pymongo
import datetime
import random
import heapq
from functools import total_ordering
from pymongo_schema.extract import extract_collection_schema
from typing import Dict, List, Optional
from common.datetime_utils import datetime_to_milliseconds, milliseconds_to_datetime
from .logging import logger


@total_ordering
class ComparableQueryResult(object):
    def __init__(self, key, q_result):
        self.key = key
        self.q_result = q_result

    def __lt__(self, other):
        return self.key < other.key

    def __eq__(self, other):
        return self.key == other.key

    def __repr__(self):
        return '{0.__class__.__name__}(key={0.key}, q_result={0.q_result})'.format(self)


class ContentStore(object):
    def __init__(self, connection_string: str, db: str):
        self.client = pymongo.MongoClient(connection_string)
        self.db = self.client[db]
        self.collection = self.db['broccoli.server']

    def append(self, doc: Dict, idempotency_key: str):
        if idempotency_key not in doc:
            logger.error(f"Idempotency key {idempotency_key} is not found in payload {doc}")
            return

        idempotency_value = doc[idempotency_key]
        existing_doc_count = self.collection.count_documents({idempotency_key: idempotency_value})
        if existing_doc_count != 0:
            logger.info(f"Document with {idempotency_key}={idempotency_value} is already present")
            return

        # todo: insert fails?
        doc["created_at"] = datetime.datetime.utcnow()
        self.collection.insert(doc)

    def query(self, q: Dict, limit: Optional[int] = None, projection: Optional[List[str]] = None,
              sort: Optional[Dict[str, int]] = None, datetime_q: Optional[List[Dict]] = None) -> List[Dict]:
        # Append datetime query
        if datetime_q:
            for qd in datetime_q:
                q[qd["key"]] = {
                    "$" + qd["op"]: milliseconds_to_datetime(qd["value"])
                }

        # Append default projections
        if projection:
            projection += ["_id", "created_at"]
        # todo: find fails?
        cursor = self.collection.find(q, projection=projection)

        # Append limit
        if limit:
            cursor = cursor.limit(limit)

        # Append sort
        if sort:
            for sort_key, sort_order in sort.items():
                cursor = cursor.sort(sort_key, sort_order)

        res = []
        for document in cursor:
            document["_id"] = str(document["_id"])
            document["created_at"] = datetime_to_milliseconds(document["created_at"])
            res.append(document)
        return res

    def update_one(self, filter_q: Dict, update_doc: Dict):
        existing_doc_count = self.collection.count_documents(filter_q)
        if existing_doc_count == 0:
            logger.info(f"Document with query {filter_q} does not exist")
            return

        if existing_doc_count > 1:
            logger.info(f"More than one document with query {filter_q} exists")
            return

        # todo: update_one fails
        self.collection.update_one(filter_q, update_doc, upsert=False)

    def schema(self) -> List[str]:
        field_names = []
        extracted_schema = extract_collection_schema(self.collection)["object"]
        for field_name, _ in extracted_schema.items():
            if field_name != "_id":
                field_names.append(field_name)
        return field_names

    def update_one_binary_string(self, filter_q: Dict, key: str, binary_string: str):
        if not ContentStore._check_if_string_is_binary(binary_string):
            logger.info(f"from_binary_string {binary_string} is not a 01 string")
            return
        self.update_one(filter_q, {
            "$set": {
                key: binary_string
            }
        })

    def query_nearest_hamming_neighbors(self, q: Dict, binary_string_key: str, from_binary_string: str,
                                        max_distance: int) -> List[Dict]:
        # todo: use a metric tree
        # todo: various failure case here
        if not ContentStore._check_if_string_is_binary(from_binary_string):
            return []
        results = []
        for q_result in self.query(q, limit=None):
            if not ContentStore._check_if_q_result_has_valid_binary(q_result, binary_string_key, from_binary_string):
                continue
            q_binary_string = q_result[binary_string_key]
            distance = ContentStore._compute_binary_hamming_distance(q_binary_string, from_binary_string)
            if distance <= max_distance:
                results.append(q_result)
        return results

    def query_n_nearest_hamming_neighbors(self, q: Dict, binary_string_key: str, from_binary_string: str,
                                          pick_n: int) -> List[Dict]:
        # todo: use a metric tree
        if not ContentStore._check_if_string_is_binary(from_binary_string):
            logger.info(f"from_binary_string {from_binary_string} is not a 01 string")
            return []
        q_results = self.query(q, limit=None)
        if len(q_results) < pick_n:
            return []
        results = []
        heapq.heapify(results)
        for q_result in q_results:
            if not ContentStore._check_if_q_result_has_valid_binary(q_result, binary_string_key, from_binary_string):
                continue
            q_binary_string = q_result[binary_string_key]
            distance = ContentStore._compute_binary_hamming_distance(q_binary_string, from_binary_string)
            heapq.heappush(results, ComparableQueryResult(-distance, q_result))
            if len(results) > pick_n:
                heapq.heappop(results)
        return list(map(lambda h_item: h_item.q_result, results))

    @staticmethod
    def _check_if_string_is_binary(string: str) -> bool:
        if not (set(string) <= set("01")):
            logger.info(f"{string} is not a 01 string")
            return False
        return True

    @staticmethod
    def _check_if_q_result_has_valid_binary(q_result: Dict, binary_string_key: str, from_binary_string: str) -> bool:
        if binary_string_key not in q_result:
            logger.info(f"Document {q_result} does not have field {binary_string_key}")
            return False
        q_binary_string = q_result[binary_string_key]
        if len(q_binary_string) != len(from_binary_string):
            logger.info(f"Document {q_result} does not have string '{binary_string_key}' of the queried length "
                        f"{len(q_binary_string)}")
            return False
        if not ContentStore._check_if_string_is_binary(q_binary_string):
            return False
        return True

    @staticmethod
    def _compute_binary_hamming_distance(s1: str, s2: str):
        distance = 0
        for i in range(len(s1)):
            if s1[i] != s2[i]:
                distance += 1
        return distance

    def random_one(self, q: Dict, projection: List[str]) -> Dict:
        documents = self.query(q, projection=projection)
        random_index = random.randint(0, len(documents) - 1)
        return documents[random_index]

    def count(self, q: Dict) -> int:
        return self.collection.count_documents(q)
