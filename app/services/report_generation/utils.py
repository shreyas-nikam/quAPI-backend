from operator import itemgetter
from pathlib import Path
import re
from typing import List
from llama_index.core.schema import NodeWithScore, TextNode
import os
import pickle
from llama_index.core import SummaryIndex, VectorStoreIndex, StorageContext, load_index_from_storage






# function tools
def chunk_retriever_fn(index, query: str) -> List[NodeWithScore]:
    """Retrieves a small set of relevant document chunks from the corpus.

    ONLY use for research questions that want to look up specific facts from the knowledge corpus,
    and don't need entire documents.

    """
    retriever = index.as_retriever(similarity_top_k=5)
    nodes = retriever.retrieve(query)
    return nodes



def _get_document_nodes(
    summary_indexes: dict,
    nodes: List[NodeWithScore], 
    top_n: int = 5
) -> List[NodeWithScore]:
    """Get document nodes from a set of chunk nodes.

    Given chunk nodes, "de-reference" into a set of documents, with a simple weighting function (cumulative total) to determine ordering.

    Cutoff by top_n.

    """
    file_paths = {n.metadata["file_path"] for n in nodes}
    file_path_scores = {f: 0 for f in file_paths}
    for n in nodes:
        file_path_scores[n.metadata["file_path"]] += n.score

    # Sort file_path_scores by score in descending order
    sorted_file_paths = sorted(
        file_path_scores.items(), key=itemgetter(1), reverse=True
    )
    # Take top_n file paths
    top_file_paths = [path for path, score in sorted_file_paths[:top_n]]

    # use summary index to get nodes from all file paths
    all_nodes = []
    for file_path in top_file_paths:
        # NOTE: input to retriever can be blank
        all_nodes.extend(
            summary_indexes[Path(file_path).name].as_retriever().retrieve("")
        )

    return all_nodes


def doc_retriever_fn(index, summary_indexes, query: str) -> float:
    """Document retriever that retrieves entire documents from the corpus.

    ONLY use for research questions that may require searching over entire research reports.

    Will be slower and more expensive than chunk-level retrieval but may be necessary.
    """
    retriever = index.as_retriever(similarity_top_k=5)
    nodes = retriever.retrieve(query)
    return _get_document_nodes(summary_indexes, nodes)


# utility functions
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


def get_text_nodes(json_dicts, file_path, image_dir=None):
    """Split docs into nodes, by separator."""
    nodes = []

    image_files = _get_sorted_image_files(image_dir) if image_dir is not None else None
    md_texts = [d["md"] for d in json_dicts]

    for idx, md_text in enumerate(md_texts):
        chunk_metadata = {
            "page_num": idx + 1,
            "parsed_text_markdown": md_text,
            "file_path": file_path,
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

def make_dicts(files, input_dir, out_image_dir, parser):
    # Create dictionaries for each file
    file_dicts = {}
    for file_path in files:
        file_base = Path(file_path).stem
        full_file_path = str(Path(input_dir) / file_path)
        md_json_objs = parser.get_json_result(full_file_path)
        json_dicts = md_json_objs[0]["pages"]

        image_path = str(Path(out_image_dir) / file_base)
        image_dicts = parser.get_images(md_json_objs, download_path=image_path)

        file_dicts[file_path] = {
            "file_path": full_file_path,
            "json_dicts": json_dicts,
            "image_path": image_path,
        }
    return file_dicts



def combine_dicts(file_dicts, output_path="app/data/outputs"):
    # this will combine all nodes from all files into a single list
    all_text_nodes = []
    text_nodes_dict = {}
    for file_path, file_dict in file_dicts.items():
        json_dicts = file_dict["json_dicts"]
        text_nodes = get_text_nodes(
            json_dicts, file_dict["file_path"], image_dir=file_dict["image_path"]
        )
        all_text_nodes.extend(text_nodes)
        text_nodes_dict[file_path] = text_nodes
    
    pickle.dump(text_nodes_dict, open(f"{output_path}/text_nodes.pkl", "wb"))
    
    return all_text_nodes, text_nodes_dict


def load_processed_data(output_path="app/data/outputs"):
    
    text_nodes_dict = pickle.load(open(f"{output_path}/text_nodes.pkl", "rb"))
    all_text_nodes = []
    for _, text_nodes in text_nodes_dict.items():
        all_text_nodes.extend(text_nodes)
    return all_text_nodes, text_nodes_dict

def load_index(text_nodes_dict, files, output_path="app/data/outputs", rebuild_index=False):
    # Vector Indexing
    if not os.path.exists(f"{output_path}/storage_nodes") or rebuild_index:
        text_nodes = []
        for paper_path, text_nodes in text_nodes_dict.items():
            text_nodes.extend(text_nodes)
        index = VectorStoreIndex(text_nodes)
        # save index to disk
        index.set_index_id("vector_index")
        index.storage_context.persist(f"{output_path}/storage_nodes")
    else:
        # rebuild storage context
        storage_context = StorageContext.from_defaults(persist_dir=f"{output_path}/storage_nodes")
        # load index
        index = load_index_from_storage(storage_context, index_id="vector_index")
    
    
    # Summary Index dictionary - store map from file path to a summary index around it
    summary_indexes = {
        file_path: SummaryIndex(text_nodes_dict[file_path]) for file_path in files
    }

    return index, summary_indexes
