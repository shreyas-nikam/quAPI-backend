import nest_asyncio
from dotenv import load_dotenv
import os
import json
import llama_index.core
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI
from llama_index.core import Settings
from llama_parse import LlamaParse
from output_renderer import ReportOutput
from app.services.report_generation.utils import chunk_retriever_fn, doc_retriever_fn
from llama_index.core.tools import FunctionTool
from app.services.report_generation.workflow import ReportGenerationAgent
from app.services.report_generation.utils import make_dicts, combine_dicts, load_processed_data, load_index

from pathlib import Path
import pickle

# Load environment variables
load_dotenv()
nest_asyncio.apply()

# Set environment variables
PHOENIX_API_KEY = os.getenv("PHOENENIX_API_KEY")
OPENAI_KEY = os.getenv("OPENAI_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL")
OUT_IMAGE_DIR = "output_images"
REPORT_GENERATION_PROMPT = json.load(open("app/data/prompts.json" , "r"))["REPORT_GENERATION_PROMPT"]
os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"api_key={PHOENIX_API_KEY}"

# Set global handler
llama_index.core.set_global_handler(
    "arize_phoenix", endpoint="https://llamatrace.com/v1/traces"
)

# Set OpenAI models
embed_model = OpenAIEmbedding(model="text-embedding-3-large", api_key=OPENAI_KEY)
llm = OpenAI(model=OPENAI_MODEL, api_key=OPENAI_KEY)
report_gen_llm = OpenAI(model=OPENAI_MODEL, system_prompt=REPORT_GENERATION_PROMPT, api_key=OPENAI_KEY)

# Set settings
Settings.embed_model = embed_model
Settings.llm = llm

# load parser
parser = LlamaParse(
    result_type="markdown",
    use_vendor_multimodal_model=True,
    vendor_multimodal_model_name="anthropic-sonnet-3.5",
    api_key=OPENAI_KEY,
)

report_gen_sllm = report_gen_llm.as_structured_llm(output_cls=ReportOutput)


def create_agent(index, summary_indexes):
    chunk_retriever_tool = FunctionTool.from_defaults(fn=lambda query: chunk_retriever_fn(index, query))
    doc_retriever_tool = FunctionTool.from_defaults(fn=lambda query: doc_retriever_fn(index, summary_indexes, query))

    agent = ReportGenerationAgent(
        chunk_retriever_tool,
        doc_retriever_tool,
        llm=llm,
        report_gen_sllm=report_gen_sllm,
        verbose=True,
        timeout=60.0,
    )
    return agent


# Step 0: check if the files are already processed. if yes, return the pickled file
def check_processed(user_id, project_id):
    output_dir = f"app/data/{user_id}/{project_id}/outputs"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    if os.path.exists(f"{output_dir}/text_nodes.pkl"):
        return True
    return False

# Step 1: Load, Parse, and Index Files
def load_files(user_id, project_id, files):
    # store the files in s3
    # create output_dir
    input_dir = f"app/data/{user_id}/{project_id}/inputs"
    # move the files in the input_dir
    output_dir = f"app/data/{user_id}/{project_id}/outputs"
    output_image_dir = f"{output_dir}/output_images"
    
    # parse the files
    file_dicts = make_dicts(files, input_dir, output_image_dir, parser)

    all_text_nodes, text_nodes_dict = combine_dicts(file_dicts=file_dicts, output_dir=output_dir)

    return all_text_nodes, text_nodes_dict


async def get_response(agent, input):
    ret = await agent.run(
        input=input
    )
    return ret["response"].response

def render_report(input):
    # TODO: Implement report rendering
    print(input)


def main(user_id, project_id, input):
    if not check_processed(user_id, project_id):
        files = []
        all_text_nodes, text_nodes_dict = load_files(user_id, project_id, files)

    output_path = f"app/data/{user_id}/{project_id}/outputs"
    all_text_nodes, text_nodes_dict = load_processed_data(output_path)
    index, summary_indexes = load_index(text_nodes_dict, files, all_text_nodes, output_path)
    agent = create_agent(index, summary_indexes)
    response = get_response(agent, input)

    # render the report
    render_report(response)

    return response