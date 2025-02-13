import nest_asyncio
import llama_index.core
import os
from dotenv import load_dotenv
from llama_index.core import Settings
from llama_index.llms.openai import OpenAI
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_parse import LlamaParse
from app.utils.atlas_client import AtlasClient
from bson.objectid import ObjectId
from app.utils.s3_file_manager import S3FileManager
from pathlib import Path
from llama_index.core.schema import TextNode
from urllib.parse import quote
import os
from llama_index.core import (
    StorageContext,
    VectorStoreIndex,
)
from llama_index.vector_stores.pinecone import PineconeVectorStore
import pinecone
import logging
from pinecone import Pinecone
from pinecone import ServerlessSpec

nest_asyncio.apply()
load_dotenv()


embed_model = OpenAIEmbedding(model="text-embedding-3-large")
llm = OpenAI(timeout=120, model=os.getenv("OPENAI_MODEL"), api_key=os.getenv("OPENAI_API_KEY"))

Settings.embed_model = embed_model
Settings.llm = llm

PHOENIX_API_KEY = os.getenv("PHOENIX_API_KEY")
os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"api_key={PHOENIX_API_KEY}"
llama_index.core.set_global_handler(
    "arize_phoenix", endpoint="https://llamatrace.com/v1/traces"
)


parser = LlamaParse(
    result_type="markdown",
    use_vendor_multimodal_model=True,
    vendor_multimodal_model_name=os.getenv("OPENAI_MODEL"),
    vendor_multimodal_api_key=os.getenv("OPENAI_API_KEY"),
    api_key=os.getenv("LLAMA_CLOUD_KEY"),
)

atlas_client = AtlasClient()
s3_file_manager = S3FileManager()



logging.basicConfig(level=logging.INFO)

async def parse_file(course_id, module_id, file_id, file_url):
    """
    Parses a file, uploads images to S3, creates or updates a Pinecone index, 
    and updates the module in the database.

    Args:
        course_id (str): Course identifier.
        module_id (str): Module identifier.
        file_id (str): File identifier.
        file_url (str): URL of the file to parse.

    Returns:
        dict: Metadata about the parsed file and indexing operation.
    """
    try:
        # Validate inputs
        validate_inputs(course_id, module_id, file_id, file_url)

        # Parse the file
        md_json_objs = parser.get_json_result(file_url)
        json_dicts = md_json_objs[0]["pages"]
        out_image_dir = Path("outputs/") / file_id / "images"
        out_image_dir.mkdir(parents=True, exist_ok=True)

        image_dicts = parser.get_images(md_json_objs, download_path=str(out_image_dir))
        refactored_image_paths = await upload_images_to_s3(image_dicts, course_id, module_id)

        # Prepare text nodes for indexing
        all_text_nodes = prepare_text_nodes(json_dicts, file_url)

        # Get or create Pinecone index
        index_name = await get_or_create_index(course_id, module_id, all_text_nodes)

        # Update the database with the index information
        update_module_in_db(course_id, module_id, index_name)

        logging.info("File parsing and indexing completed successfully.")

        return {
            'node_id': ObjectId(),
            "file_id": file_id,
            "index_name": index_name,
            "uploaded_images": refactored_image_paths,
        }
    except Exception as e:
        logging.error(f"An error occurred while processing the file: {e}")
        raise


def validate_inputs(course_id, module_id, file_id, file_url):
    """
    Validates the inputs for the file parsing operation.
    """
    if not all([course_id, module_id, file_id, file_url]):
        raise ValueError("All inputs (course_id, module_id, file_id, file_url) must be provided.")
    if not file_url.startswith("http"):
        raise ValueError("Invalid file_url: Must be a valid URL.")


async def upload_images_to_s3(image_dicts, course_id, module_id):
    """
    Uploads images to S3 and updates paths in the image dictionaries.

    Args:
        image_dicts (list): List of image dictionaries with file paths.
        course_id (str): Course identifier.
        module_id (str): Module identifier.

    Returns:
        list: List of updated image dictionaries with S3 paths.
    """
    refactored_image_paths = []
    for image in image_dicts:
        try:
            path = image["path"]
            key = f"qu-course-design/{course_id}/{module_id}/raw_resources/{image['name']}"
            await s3_file_manager.upload_file(path, key)
            key = quote(key)
            resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"
            image["path"] = resource_link
            refactored_image_paths.append(image)
        except Exception as e:
            logging.error(f"Failed to upload image {image['name']} to S3: {e}")
            raise
    return refactored_image_paths


def prepare_text_nodes(json_dicts, file_url):
    """
    Prepares a list of TextNode objects from parsed JSON.

    Args:
        json_dicts (list): List of parsed JSON dictionaries.
        file_url (str): File URL.

    Returns:
        list: List of TextNode objects.
    """
    text_nodes = []
    for json_dict in json_dicts:
        text_node = TextNode(
            text="",
            metadata={
                "page_num": json_dict["page"],
                "parsed_text_markdown": json_dict["md"],
                "file_path": file_url,
                "images": json_dict.get("images"),
            },
        )
        text_nodes.append(text_node)
    return text_nodes


async def get_or_create_index(course_id, module_id, text_nodes, index_id):
    """
    Retrieves or creates a Pinecone index for the given module.

    Args:
        course_id (str): Course identifier.
        module_id (str): Module identifier.
        text_nodes (list): List of TextNode objects.

    Returns:
        str: Name of the Pinecone index.
    """
    try:
        pc = Pinecone(
            api_key=os.environ.get("PINECONE_API_KEY")
        )
        
        if pc.list_indexes().names().count(index_id) > 0:
            logging.info(f"Using existing Pinecone index: {index_id}")
            vector_store = PineconeVectorStore(pc.Index(name=index_id))
            index = VectorStoreIndex.from_vector_store(vector_store=vector_store)
        else:
            logging.info(f"Creating new Pinecone index: {index_id}")
            pc.create_index(
                index_id,
                dimension=1536,
                metric="euclidean",
                spec=ServerlessSpec(
                    cloud="aws",
                    region="us-east-1"
                ),
            )
            storage_context = StorageContext.from_defaults(
                vector_store=PineconeVectorStore(
                    pinecone.Index(name=index_id, 
                                   api_key=os.environ.get("PINECONE_API_KEY"),
                                   host="us-east-1.pinecone.io"), 
                    api_key=os.environ.get("PINECONE_API_KEY")
                )
            )
            index = VectorStoreIndex.from_vector_store(vector_store=storage_context.vector_store)
            await index.storage_context.vector_store.async_add(text_nodes)
            index.insert_nodes(text_nodes)

        return index
    except Exception as e:
        logging.error(f"Failed to create or retrieve Pinecone index: {e}")
        raise


def update_module_in_db(course_id, module_id, index_name):
    """
    Updates the module in the database with the index name.

    Args:
        course_id (str): Course identifier.
        module_id (str): Module identifier.
        index_name (str): Name of the Pinecone index.
    """
    try:
        course = atlas_client.find("course_design", {"_id": ObjectId(course_id)})[0]
        modules = course["modules"]
        module = next((m for m in modules if m["module_id"] == ObjectId(module_id)), None)

        if module:
            module["index"] = index_name
            atlas_client.update(
                "course_design",
                {"_id": ObjectId(course_id)},
                {"$set": {"modules": modules}},
            )
            logging.info(f"Updated module {module_id} with index {index_name}.")
        else:
            raise ValueError(f"Module with ID {module_id} not found.")
    except Exception as e:
        logging.error(f"Failed to update module in the database: {e}")
        raise
