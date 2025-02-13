# get the files from frontend
# store the files in s3
# store the file locations in mongodb in resources
# add file
# delete file
from app.utils.s3_file_manager import S3FileManager
from app.utils.atlas_client import AtlasClient
from bson.objectid import ObjectId
from urllib.parse import quote, unquote
from llama_parse import LlamaParse
from pathlib import Path
from dotenv import load_dotenv
import nest_asyncio
import os
import re
from copy import deepcopy
from pathlib import Path
from llama_index.core.schema import TextNode
from typing import Optional



LLAMA_KEY = os.getenv("LLAMA_CLOUD_KEY")

# Load environment variables
load_dotenv()
nest_asyncio.apply()


parser = LlamaParse(
    result_type="markdown",
    use_vendor_multimodal_model=True,
    vendor_multimodal_model_name="anthropic-sonnet-3.5",
    api_key=LLAMA_KEY,
)


# Utility functions _________________________________________________________________________________________

def get_page_number(file_name):
    match = re.search(r"-page-(\d+)\.jpg$", str(file_name))
    if match:
        return int(match.group(1))
    return 0

def _get_sorted_image_files(image_dir):
    """Get image files sorted by page."""
    raw_files = [f for f in list(Path(image_dir).iterdir()) if f.is_file()]
    sorted_files = sorted(raw_files, key=get_page_number)
    return sorted_files

def get_text_nodes(json_dicts, paper_path, image_dir=None):
    """Split docs into nodes, by separator."""
    nodes = []

    image_files = _get_sorted_image_files(image_dir) if image_dir is not None else None
    md_texts = [d["md"] for d in json_dicts]

    for idx, md_text in enumerate(md_texts):
        chunk_metadata = {
            "page_num": idx + 1,
            "parsed_text_markdown": md_text,
            "paper_path": paper_path,
        }
        if image_files is not None:
            image_file = image_files[idx]
            chunk_metadata["image_path"] = str(image_file)
        chunk_metadata["parsed_text_markdown"] = md_text
        node = TextNode(
            text="",
            metadata=chunk_metadata,
        )
        nodes.append(node)

    return nodes


# ____________________________________________________________________________________________________________


async def add_file(collection_name, collection_id, file):
    s3 = S3FileManager()
    atlas_client = AtlasClient()

    resource_id = ObjectId()
    key = f"{collection_name}/{collection_id}/raw_resources/{resource_id}/{file.filename}"
    # Upload file to S3
    await s3.upload_file_from_frontend(file, key)
    key = quote(key)
    resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"
    resource={
        "resource_id": resource_id,
        "resource_link": resource_link,
        "resource_name": file.filename,
        "resource_id": resource_id,
        "resource_type": "File",
    }

    # CHECK 1
    md_json_objs = parser.get_json_result(resource_link)
    json_dicts = md_json_objs[0]["pages"]

    # store the images
    # make the image path if it doesn't exist
    image_path = str(Path("outputs") / resource_id / "images")
    os.makedirs(image_path, exist_ok=True)
    image_dicts = parser.get_images(md_json_objs, download_path=image_path)

    # upload the images to s3
    for image_dict in image_dicts:
        image_key = f"{collection_name}/{collection_id}/raw_resources/{resource_id}/images/{image_dict['name']}"
        await s3.upload_file(image_dict["image_path"], image_key)
        image_key = quote(image_key)
        image_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{image_key}"
        image_dict["image_link"] = image_link

    file_dict = {
        "file_path": resource_link,
        "json_dicts": json_dicts,
        "image_path": image_path,
    }

    return file_dict

    
async def add_files(collection_name, collection_id, files):
    file_dicts = {}
    for file in files:
        file_dict = await add_file(collection_name, collection_id, file)

        # Check 2 requires file path not name 
        file_dicts[file.filename] = file_dict

    return file_dicts


def combine_files(file_dicts):
    # this will combine all nodes from all papers into a single list
    all_text_nodes = []
    text_nodes_dict = {}
    for paper_path, paper_dict in file_dicts.items():
        json_dicts = paper_dict["json_dicts"]
        text_nodes = get_text_nodes(
            json_dicts, paper_dict["file_path"], image_dir=paper_dict["image_path"]
        )
        all_text_nodes.extend(text_nodes)
        text_nodes_dict[paper_path] = text_nodes

# TODO
async def delete_file(collection_name, collection_id, resource_id):
    s3 = S3FileManager()
    atlas_client = AtlasClient()

    # Delete the resource from the database
    collection = atlas_client.find(collection_name, filter={"_id": ObjectId(collection_id)})
    if not collection:
        return False
    
    collection = collection[0]
    resources = collection["raw_resources"]
    resource_to_be_deleted = None
    remaining_resources = []
    
    for resource in resources:
        if resource["resource_id"] == resource_id:
            resource_to_be_deleted = resource
        else:
            remaining_resources.append(resource)

    resource_link = resource_to_be_deleted["resource_link"]
    await s3.delete_file(resource_link)

    atlas_client.update(collection_name, filter={"_id": ObjectId(collection_id)}, update={"$set": {"raw_resources": remaining_resources}})

    #TODO: delete the resource from the vector store/index/dicts as well
    
    return True
