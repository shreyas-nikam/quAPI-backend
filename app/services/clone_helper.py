import logging
from app.utils.atlas_client import AtlasClient
import re
import copy
from bson import ObjectId
from app.utils.s3_file_manager import S3FileManager


# Regex to detect an S3 link (very simplistic example).
# Adjust for your actual S3 URL format.
S3_LINK_REGEX = re.compile(r'^https?://.*\.amazonaws\.com/.*')

# Regex to detect 24-hex-character IDs inside the S3 link
# (typical MongoDB ObjectId shape, e.g. 507f1f77bcf86cd799439011)
OBJECT_ID_REGEX = re.compile(r'[0-9a-fA-F]{24}')

def is_s3_link(url: str) -> bool:
    """Return True if the string looks like an S3 link."""
    return bool(S3_LINK_REGEX.match(url))

def extract_ids_from_link(s3_link: str):
    """Extract all IDs found (via regex) in the S3 link."""
    return OBJECT_ID_REGEX.findall(s3_link)

def rewrite_s3_link(s3_link: str, id_map: dict) -> str:
    """
    For each old_id found in the link, replace it with a new id.
    This function modifies the string to produce a new S3 link
    that references the new IDs.
    """
    # For each ID found, replace with the new ID from the id_map (creating one if needed).
    def replacer(match):
        old_id = match.group(0)
        if old_id not in id_map:
            id_map[old_id] = str(ObjectId())  # or use uuid4() or any ID generator
        return id_map[old_id]
    
    # Replacing all occurrences in the link
    new_link = OBJECT_ID_REGEX.sub(replacer, s3_link)
    return new_link

def copy_s3_object(old_link: str, new_link: str):
    """
    Stubbed-out function for copying an S3 object from old_link to new_link.
    In real usage, replace with actual S3 copy logic using boto3 or similar.
    """
    logging.info(f"[DEBUG] Copying from:\n  {old_link}\nto:\n  {new_link}")
    s3_file_manager = S3FileManager()
    old_key = old_link.split("https://qucoursify.s3.us-east-1.amazonaws.com/")[1]
    new_key = new_link.split("https://qucoursify.s3.us-east-1.amazonaws.com/")[1]
    s3_file_manager.copy_file(old_key, new_key)
    

def clone_mongodb_json_entry(data, id_map=None):
    """
    Recursively clone a MongoDB JSON-like structure (dicts/lists),
    remapping:
      - '_id' or '*_id' fields to new IDs
      - S3 links to new S3 links (with new IDs in them)
    
    :param data:  The nested JSON/dict/list object.
    :param id_map: A dict to remember old_id => new_id mappings.
    :return: A new object with all transformations applied.
    """
    if id_map is None:
        id_map = {}
    
    if isinstance(data, dict):
        new_dict = {}
        for key, value in data.items():
            # If the key is "_id" or ends in "_id", remap the ID
            if key == "_id" or key.endswith("_id"):
                old_id = value
                if old_id not in id_map:
                    id_map[old_id] = str(ObjectId())  # or use your chosen ID generator
                new_dict[key] = ObjectId(id_map[old_id])
            else:
                # Recursively handle child objects
                new_dict[key] = clone_mongodb_json_entry(value, id_map)
        return new_dict
    
    elif isinstance(data, list):
        # Handle each item in the list recursively
        return [clone_mongodb_json_entry(item, id_map) for item in data]
    
    elif isinstance(data, str):
        # Check if it's an S3 link
        if is_s3_link(data):
            # Extract & remap IDs found in the link
            new_link = rewrite_s3_link(data, id_map)
            # Perform actual S3 copy from old to new link
            copy_s3_object(data, new_link)
            return new_link
        else:
            # It's just a normal string
            return data
    
    else:
        # For numbers, booleans, None, etc. just return them
        return data


def clone_entry(id, collection):
    atlas_client = AtlasClient()
    entry = atlas_client.find(collection, {"_id": ObjectId(id)})
    if not entry:
        logging.info(f"Entry with id {id} not found in collection {collection}")
        return None
    entry = entry[0]

    cloned_entry = clone_mongodb_json_entry(entry)
    atlas_client.insert(collection, cloned_entry)
    return cloned_entry
