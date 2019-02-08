import pymongo
from typing import Dict, List, Tuple
from worker_manager.logger import logger
from worker_manager.load_object import load_object


# todo: abstract it out
# todo: properly close all resources
client = pymongo.MongoClient('localhost', 27017)
db = client['broccoli']
collection = db['broccoli.workers']


def add(module: str, class_name: str, args: Dict, global_args: List[str], worker_globals: Dict, interval_seconds: int) \
        -> Tuple[bool, str]:
    # todo: garbage collect this w?
    status, worker_or_message = load_object(module, class_name, args, global_args, worker_globals)
    if not status:
        logger.error(f"Fails to add worker module={module} class_name={class_name} args={args} "
                     f"global_args={global_args}, message {worker_or_message}")
        return False, worker_or_message
    worker_id = worker_or_message._id
    existing_doc_count = collection.count_documents({"worker_id": worker_id})
    if existing_doc_count != 0:
        return False, f"Worker with id {worker_id} already exists"
    # todo: insert fails?
    collection.insert({
        "worker_id": worker_id,
        "module": module,
        "class_name": class_name,
        "args": args,
        "global_args": global_args,
        "interval_seconds": interval_seconds
    })
    return True, worker_id


def get_all() -> Dict[str, Tuple[str, str, Dict, List[str], int]]:
    res = {}
    # todo: find fails?
    for document in collection.find():
        res[document["worker_id"]] = (
            document["module"],
            document["class_name"],
            document["args"],
            document["global_args"],
            document["interval_seconds"]
        )
    return res


def remove(worker_id: str) -> Tuple[bool, str]:
    existing_doc_count = collection.count_documents({"worker_id": worker_id})
    if existing_doc_count == 0:
        return False, f"Worker with id {worker_id} does not exist"
    # todo: delete_one fails?
    collection.delete_one({"worker_id": worker_id})
    return True, ""


def update_interval_seconds(worker_id: str, interval_seconds: int) -> Tuple[bool, str]:
    existing_doc_count = collection.count_documents({"worker_id": worker_id})
    if existing_doc_count == 0:
        return False, f"Worker with id {worker_id} does not exist"
    # todo: update_one fails
    collection.update_one({"worker_id": worker_id}, {"$set": {"interval_seconds": interval_seconds}})
    return True, ""