# Standard library imports
import datetime
import time
import random
import json
import ast
import os
import logging
import shutil
from pathlib import Path
from urllib.parse import urlparse, quote, unquote
import mimetypes

# Third-party library imports
import requests
from fastapi import HTTPException, UploadFile
from bson.objectid import ObjectId
from openai import OpenAI
from langchain_core.prompts import PromptTemplate
from google import genai
from litellm import check_valid_key

# Application-specific imports
from app.services.report_generation.generate_pdf import convert_markdown_to_pdf
from app.utils.llm import LLM
from app.utils.s3_file_manager import S3FileManager
from app.utils.atlas_client import AtlasClient
from app.services.github_helper_functions import create_repo_in_github, upload_file_to_github, update_file_in_github, create_github_issue, delete_repo_from_github
from app.services.metaprompt import generate_prompt
from app.services.user_services import quAPIVault

LAB_DESIGN_STEPS = [
    "raw_resources", #automatic
    "idea",
    "business_use_case", #automatic
    "technical_specifications", #expert-review-step
    "review_project", #automatic
    "deliverables", #automatic
]


def _get_lab(lab_id):
    atlas_client = AtlasClient()
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})
    if not lab:
        return "Lecture not found", None
    
    lab = lab[0]
    
    return lab, None

def _get_prompt(prompt_name):
    """
    Get the prompt template

    Args:
    prompt_name: str - the name of the prompt

    Returns:
    PromptTemplate: the prompt template
    """
    prompts_file = "app/data/prompts.json"
    with open(prompts_file, "r") as file:
        prompts = json.load(file)
    if prompt_name not in prompts:
        logging.error(f"Prompt {prompt_name} not found")
        return ""
    return prompts[prompt_name]

def _get_response_from_llm(llm, prompt, inputs, output_type="json"):
    """
    Get the response from the LLM

    Args:
    llm: LLM - the LLM object
    prompt: PromptTemplate - the prompt template
    inputs: dict - the inputs for the prompt
    output_type: str - the type of output to be returned

    Returns:
    dict: the response from the LLM
    """
    # Try multiple times
    trials = 5
    for _ in range(trials):
        try:
            time.sleep(random.randint(1, 3))

            response = llm.get_response(prompt, inputs=inputs)
            logging.info(f"Processed response: {response}")

            if output_type == "json":
                return json.loads(response[response.index("{"):response.rindex("}")+1])

            elif output_type == "list":
                return ast.literal_eval(response[response.index("["):response.rindex("]")+1])

            else:
                return response

        except Exception as e:
            logging.error(f"Error in getting response: {e}")
            continue

    raise Exception("Something went wrong. Please try again later.")

def _get_response(llm, prompt, inputs, output_type="json"):
    # try with chatgpt first and then with gemini
    try:
        llm = LLM("chatgpt")
        response = _get_response_from_llm(llm, prompt, inputs, output_type)
        return response
    except Exception as e:
        logging.error(f"Error in getting response from chatgpt: {e}")
    
    try:
        llm = LLM("gemini")
        response = _get_response_from_llm(llm, prompt, inputs, output_type)
        return response
    except Exception as e:
        logging.error(f"Error in getting response from gemini: {e}")

    raise Exception("Something went wrong. Please try again later.")

def _convert_object_ids_to_strings(data):
    if isinstance(data, dict):
        return {key: _convert_object_ids_to_strings(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [_convert_object_ids_to_strings(item) for item in data]
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data

def _get_file_type(file: UploadFile):
    if file.content_type.startswith("image"):
        return "Image"
    elif file.content_type.startswith("text"):
        return "Note"
    else:
        return "File"

async def get_labs(username):
    atlas_client = AtlasClient()
    labs = atlas_client.find("lab_design")
    user_labs = []
    for lab in labs:
        users = lab.get('users', [])
        if username in users:
            user_labs.append(lab)
    labs = _convert_object_ids_to_strings(user_labs)
    return labs
    
# generate_course_outline -> take in the input as the file and the instructions and generate the course outline
async def generate_lab_outline(files, instructions, use_metaprompt=False):

    lab_outline_instructions = _get_prompt("LAB_OUTLINE_PROMPT")

    lab_outline_instructions += f"\n\nUser's instructions:\n{instructions}"

    if use_metaprompt:
        lab_outline_instructions = await generate_prompt(lab_outline_instructions)

    if lab_outline_instructions == "The request timed out. Please try again.":
        lab_outline_instructions = _get_prompt("LAB_OUTLINE_PROMPT")
        lab_outline_instructions += f"\n\nUser's instructions:\n{instructions}"

    client = OpenAI(timeout=120, api_key=os.getenv("OPENAI_KEY"))

    assistant_files_streams = []
    for file in files:
        file_content = file.file.read()

        file.file.seek(0)

        assistant_files_streams.append((file.filename, file_content))

    # Track created resources
    created_assistant_id = None
    created_vector_store_id = None
    created_thread_id = None

    try:
        assistant = client.beta.assistants.create(
            name="Lecture outline creator",
            instructions=lab_outline_instructions,
            model=os.getenv("OPENAI_MODEL"),
            tools=[{"type": "file_search"}]
        )
        created_assistant_id = assistant.id  # Track the assistant

        vector_store = client.beta.vector_stores.create(
            name="Lecture Resources",
            expires_after={"days": 1, "anchor": "last_active_at"},
        )
        created_vector_store_id = vector_store.id  # Track the vector store

        file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
            vector_store_id=vector_store.id, files=assistant_files_streams
        )

        assistant = client.beta.assistants.update(
            assistant_id=assistant.id,
            tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
        )

        thread = client.beta.threads.create(
            messages=[{
                "role": "user",
                "content": "Create the lab outline based on the instructions provided"
            }]
        )
        created_thread_id = thread.id  # Track the thread

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id, assistant_id=assistant.id, poll_interval_ms=10000
        )

        messages = list(client.beta.threads.messages.list(thread_id=thread.id, run_id=run.id))
        message_content = messages[0].content[0].text
        annotations = message_content.annotations
        citations = []

        for index, annotation in enumerate(annotations):
            message_content.value = message_content.value.replace(annotation.text, f"[{index}]")
            if file_citation := getattr(annotation, "file_citation", None):
                cited_file = client.files.retrieve(file_citation.file_id)
                citations.append(f"[{index}] {cited_file.filename}")

        response = message_content.value
    except Exception as e:
        logging.error(f"Error in generating lab outline: {e}")
        return "The request timed out. Please try again later. However, here's a sample response:\n\n# Slide 1: **On Machine Learning Applications in Investments**\n**Description**: This module provides an overview of the use of machine learning (ML) in investment practices, including its potential benefits and common challenges. It highlights examples where ML techniques have outperformed traditional investment models.\n\n**Learning Outcomes**:\n- Understand the motivations behind using ML in investment strategies.\n- Recognize the challenges and solutions in applying ML to finance.\n- Explore practical applications of ML for predicting equity returns and corporate performance.\n### Slide 2: **Alternative Data and AI in Investment Research**\n**Description**: This module explores how alternative data sources combined with AI are transforming investment research by providing unique insights and augmenting traditional methods.\n\n**Learning Outcomes**:\n- Identify key sources of alternative data and their relevance in investment research.\n- Understand how AI can process and derive actionable insights from alternative data.\n- Analyze real-world use cases showcasing the impact of AI in research and decision-making.\n### Slide 3: **Data Science for Active and Long-Term Fundamental Investing**\n**Description**: This module covers the integration of data science into long-term fundamental investing, discussing how quantitative analysis can enhance traditional methods.\n\n**Learning Outcomes**:\n- Learn the foundational role of data science in long-term investment strategies.\n- Understand the benefits of combining data science with active investing.\n- Evaluate case studies on the effective use of data science to support investment decisions.\n### Slide 4: **Unlocking Insights and Opportunities**\n**Description**: This module focuses on techniques and strategies for using data-driven insights to identify market opportunities and enhance investment management processes.\n\n**Learning Outcomes**:\n- Grasp the importance of leveraging advanced data analytics for opportunity identification.\n- Understand how to apply insights derived from data to optimize investment outcomes.\n- Explore tools and methodologies that facilitate the unlocking of valuable investment insights.\n### Slide 5: **Advances in Natural Language Understanding for Investment Management**\n**Description**: This module highlights the progression of natural language understanding (NLU) and its application in finance. It covers recent developments and their implications for asset management.\n\n**Learning Outcomes**:\n- Recognize advancements in NLU and their integration into investment strategies.\n- Explore trends and applications of NLU in financial data analysis.\n- Understand the technical challenges and solutions associated with implementing NLU tools.\n###"
    finally:
        # Clean up all created resources to avoid charges
        if created_assistant_id:
            client.beta.assistants.delete(created_assistant_id)
        if created_vector_store_id:
            client.beta.vector_stores.delete(created_vector_store_id)
        if created_thread_id:
            client.beta.threads.delete(created_thread_id)

    return response

# clone_course -> takes in the course_id and clones the course
async def clone_lab(lab_id):
    
    atlas_client = AtlasClient()
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return "Lecture not found"
    
    lab = lab[0]
    lab.pop("_id")

    # recursively iterate through the modules and resources and clone them. if it contains _id, replace it with a new ObjectId
    def clone(data):
        if isinstance(data, dict):
            for key, value in data.items():
                if key.endsWith("_id"):
                    data[key] = ObjectId()
                else:
                    data[key] = clone(value)
        elif isinstance(data, list):
            for index, item in enumerate(data):
                data[index] = clone(item)
        return data

    atlas_client.insert("lab_design", lab)

    lab = _convert_object_ids_to_strings(lab)

    return lab


# delete_course -> takes in the course_id and deletes the course
async def delete_lab(lab_id):
    
    atlas_client = AtlasClient()
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return "Lecture not found"
    
    lab = lab[0]
    
    # delete repository from github
    delete_repo_from_github(lab_id)
    
    # TODO: remove lab from ec2 instance and its documentation if the lab is in the final stage
    
    atlas_client.delete("lab_design", filter={"_id": ObjectId(lab_id)})

    lab = _convert_object_ids_to_strings(lab)
    
    return lab
    

# create_course -> takes in the course name, course image, course description, files, course_outline, and creates a course object. also handles creation of modules
async def create_lab(username, lab_name, lab_description, lab_outline, files, lab_image):
    lab_status = "In Design Phase"

    s3_file_manager = S3FileManager()
    atlas_client = AtlasClient()

    
    # upload the course image to s3 and get the link
    lab_id = ObjectId()
    key = f"qu-lab-design/{lab_id}/lab_image/{lab_image.filename}"
    await s3_file_manager.upload_file_from_frontend(lab_image, key)
    key = quote(key)
    lab_image_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

    users = [username]

    lab = {
        "_id": lab_id,
        "users": users,
        "lab_name": lab_name,
        "lab_description": lab_description,
        "lab_image": lab_image_link,
        "lab_outline": lab_outline,
        "status": lab_status,
        "instructions": {
            "learningOutcomes": "### Learning Outcomes\n- Gain a clear understanding of the key insights derived from the uploaded document.\n- Learn how to transform raw data into interactive visualizations using Streamlit.\n- Understand the process of data preprocessing and exploration.\n- Develop an intuitive, user-friendly application that explains the underlying data concepts.",
            "datasetType": "Synthetic",
            "datasetDetails": "### Dataset Details\n- **Source**: A synthetic dataset generated to mimic the structure and characteristics of the uploaded document.\n- **Content**: Designed to include realistic data features such as numeric values, categorical variables, and time-series data where applicable.\n- **Purpose**: Serves as a sample dataset for demonstrating data handling and visualization techniques in a controlled environment.",
            "visualizationDetails": "### Visualizations Details\n- **Interactive Charts**: Incorporate dynamic line charts, bar graphs, and scatter plots to display trends and correlations.\n- **Annotations & Tooltips**: Provide detailed insights and explanations directly on the charts to help interpret the data.",
            "additionalDetails": "### Additional Details\n- **User Interaction**: Include input forms and widgets to let users experiment with different parameters and see real-time updates in the visualizations.\n- **Documentation**: Built-in inline help and tooltips to guide users through each step of the data exploration process.\n- **Reference**: Also explain how the lab idea is related to a concept in the document by referencing it."
        },
        "tags": [],
    }
    step_directory = LAB_DESIGN_STEPS[0]


    raw_resources = []
    if files:
        for file in files:
            resource_type = _get_file_type(file)

            key = f"qu-lab-design/{lab_id}/{step_directory}/{file.filename}"  
            await s3_file_manager.upload_file_from_frontend(file, key)
            key = quote(key)
            resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"    
                
            raw_resources += [{
                "resource_id": ObjectId(),
                "resource_type": resource_type,
                "resource_name": file.filename,
                "resource_description": "This is a resource file uploaded at the time of lab creation.",
                "resource_link": resource_link
            }]
    
    lab[step_directory] = raw_resources

    atlas_client.insert("lab_design", lab)

    lab = _convert_object_ids_to_strings(lab)
    # Create Repo on GitHub
    res = create_repo_in_github(lab["_id"], lab_description, private=False)
    # Create it as an object id and store the unique objectid
    return lab


def _get_resource_key_from_link(resource_link):
    resource_prefix = resource_link.split("aws.com/")[1]
    # unquote the key
    resource_key = unquote(resource_prefix)
    return resource_key


# get_course -> takes in the course_id and returns the course object
async def get_lab(lab_id):

    atlas_client = AtlasClient()
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return {}
    
    lab = lab[0]
    lab = _convert_object_ids_to_strings(lab)
    
    return lab

# add_resources_to_module -> takes in the lab_id, resource_type, resource_name, resource_description, resource_file, and adds a resource to the module and to s3
async def add_resources_to_lab(lab_id, resource_type, resource_name, resource_description, resource_file, resource_id=None, lab_design_step=0):
    s3_file_manager = S3FileManager()
    step_directory = LAB_DESIGN_STEPS[lab_design_step]
    resource_id = ObjectId() if not resource_id else ObjectId(resource_id)

    if resource_type in {"File", "Assessment", "Image", "Slide_Generated", "Slide_Content", "Video", "Dataset"}:
        # resource file is the file
        key = f"qu-lab-design/{lab_id}/{step_directory}/{str(resource_id)}."+resource_file.filename.split(".")[-1]
        await s3_file_manager.upload_file_from_frontend(resource_file, key)
        key = quote(key)
        resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

    elif resource_type == "Image":
        # resource file is the image
        key = f"qu-lab-design/{lab_id}/{step_directory}/{str(resource_id)}."+resource_file.filename.split(".")[-1]
        await s3_file_manager.upload_file_from_frontend(resource_file, key)
        key = quote(key)
        resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

    elif resource_type == "Link":
        # resource file is the resource link
        resource_description, resource_link = resource_description.split("###LINK###")

    elif resource_type == "Note" or resource_type == "Transcript":
        # resource file is the description of the note
        resource_description, resource_note = resource_description.split("###NOTE###")
        note_id = ObjectId()
        resource_file_name = str(note_id) + ".md"
        with open(resource_file_name, "w") as file:
            file.write(resource_note)

        key = f"qu-lab-design/{lab_id}/{step_directory}/{resource_file_name}"
        await s3_file_manager.upload_file(resource_file_name, key)
        key = quote(key)

        # remove the temp file
        os.remove(resource_file_name)
        resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

    atlas_client = AtlasClient()
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})
    if not lab:
        return "lab not found"
    
    lab = lab[0]
    resources = lab.get(step_directory, [])
    resource = {
        "resource_id": resource_id,
        "resource_type": resource_type,
        "resource_name": resource_name,
        "resource_description": resource_description,
        "resource_link": resource_link
    }
    resources.append(resource)
    lab[step_directory] = resources

    atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={
        "$set": {
            step_directory: resources
        }
    }
    )

    lab = _convert_object_ids_to_strings(lab)

    return lab


# delete_resource_from_module -> takes in the course_id, module_id, resource_id, and deletes the resource from the module and from s3
async def delete_resources_from_lab(lab_id, resource_id, lab_design_step=0):
    step_directory = LAB_DESIGN_STEPS[lab_design_step]

    atlas_client = AtlasClient()
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return "Lecture not found"
    
    lab = lab[0]
    resources = lab.get(step_directory, [])
    for resource in resources:
        if resource.get("resource_id") == ObjectId(resource_id):
            resources.remove(resource)
            break
    

    atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={
        "$set": {
            step_directory: resources
        }
    }
    )

    lab = _convert_object_ids_to_strings(lab)

    return lab

# replace the resource in the module and s3
async def replace_resources_in_lab(lab_id, resource_id, resource_name, resource_type, resource_description, resource_file, lab_design_step=0):
    
    # delete the resource with the resource id, and add the new resource with the same id
    lab = await delete_resources_from_lab(lab_id=lab_id,
                                                resource_id=resource_id, 
                                                lab_design_step=lab_design_step)

    # add the new resource
    lab = await add_resources_to_lab(lab_id=lab_id,
                                           resource_type=resource_type, 
                                           resource_name=resource_name, 
                                           resource_description=resource_description, 
                                           resource_file=resource_file, 
                                           resource_id=resource_id, 
                                           lab_design_step=lab_design_step)

    lab = _convert_object_ids_to_strings(lab)
    
    return lab

def _handle_s3_file_transfer(lab_id, prev_step_directory, step_directory, resources):
    s3_file_manager = S3FileManager()
    for resource in resources:
        next_step_key = f"qu-lab-design/{lab_id}/{step_directory}/{resource.get('resource_name')}"
        prev_step_key = f"qu-lab-design/{lab_id}/{prev_step_directory}/{resource.get('resource_name')}"
        s3_file_manager.copy_file(prev_step_key, next_step_key)

async def submit_lab_for_step(lab_id, lab_design_step, queue_name_suffix, instructions=""):
    step_directory = LAB_DESIGN_STEPS[lab_design_step]
    prev_step_directory = LAB_DESIGN_STEPS[lab_design_step - 1]

    lab, _ = _get_lab(lab_id=lab_id)

    if not lab:
        return "Lecture not found"

    lab["status"] = f"{queue_name_suffix.replace('_', ' ').title()}"
    if instructions:
        lab["instructions"] = instructions

    atlas_client = AtlasClient()
    atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={
        "$set": {
            "status": f"{queue_name_suffix.replace('_', ' ').title()}"
        }
    })

    prev_step_resources = lab.get(prev_step_directory, [])
    _handle_s3_file_transfer(lab_id, prev_step_directory, step_directory, prev_step_resources)

    queue_payload = {
        "lab_id": lab_id,
        "type": "lab"
    }

    if instructions:
        queue_payload["instructions"] = instructions

    atlas_client.insert(step_directory, queue_payload)

    course = _convert_object_ids_to_strings(course)

    return course



def parse_s3_url(url: str):
    parsed_url = urlparse(url)
    if parsed_url.netloc.endswith("s3.amazonaws.com"):
        # Extract bucket and key from AWS S3 URL format: https://bucket-name.s3.us-east-1.amazonaws.com/object-key
        bucket_name = parsed_url.netloc.split(".")[0]
        key = parsed_url.path.lstrip("/")
    elif parsed_url.netloc.endswith("s3.us-east-1.amazonaws.com"):
        # Extract bucket and key from AWS S3 URL format: https://bucket-name.s3.us-east-1   .amazonaws.com/object-key
        bucket_name = parsed_url.netloc.split(".")[0]
        key = parsed_url.path.lstrip("/")
    else:
        raise ValueError("Invalid S3 URL format")
    return bucket_name, key


async def fetch_note(url):
    s3_file_manager = S3FileManager()
    try:
        bucket_name, key = parse_s3_url(url)

        # Get the file from S3
        response = s3_file_manager.get_object(key=key)

        if response is None:
            return {"content": "", "content_type": "text/plain"}
        
        file_content = response["Body"].read()

        # Infer content type
        content_type = response.get("ContentType") or mimetypes.guess_type(key)[0] or "application/octet-stream"

        return {
            "content": file_content.decode("utf-8"),
            "content_type": content_type,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def fetch_quizdata(url):
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception if the request fails
        quiz_data = response.json()  # Parse the response as JSON
        return quiz_data
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error fetching quiz data: {e}")


async def convert_to_pdf_for_lab(lab_id, markdown, template_name, lab_design_step=0):

    file_id = ObjectId()
    convert_markdown_to_pdf(markdown=markdown, file_id=file_id, template_name=template_name)

    output_path = f"app/services/report_generation/outputs/{file_id}.pdf"

    key = f"qu-writing-design/{lab_id}/pre_processed_deliverables/{file_id}.pdf"
    # store the file in s3
    s3_file_manager = S3FileManager()
    await s3_file_manager.upload_file(output_path, key)

    key = quote(key)

    # store the filepath in mongodb
    atlas_client = AtlasClient()

    atlas_client.update(
        collection_name="lab_design",
        filter={"_id": ObjectId(lab_id)},
        update={
            "$set": {
                f"{LAB_DESIGN_STEPS[lab_design_step]}_pdf": f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"
            }
        }
    )

    # remove file from os
    os.remove(output_path)

    # return file url in s3
    return f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"


async def generate_idea_for_concept_lab(lab_id: str, instructions: str, prompt, use_metaprompt=False):
    if use_metaprompt:
        prompt = _get_prompt("CONCEPT_LAB_IDEA_PROMPT")
        prompt = await generate_prompt(prompt)
        
    atlas_client = AtlasClient()

    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return "Lab not found"
    
    lab = lab[0]

    if prompt == "The request timed out. Please try again.":
        prompt = _get_prompt("CONCEPT_LAB_IDEA_PROMPT")

    inputs = {
        "NAME": lab.get("lab_name"),
        "DESCRIPTION": lab.get("lab_description"),
        "INSTRUCTIONS": instructions
    }

    prompt = PromptTemplate(template=prompt, input_variables=inputs)


    llm = LLM("chatgpt")
    response = _get_response(llm, prompt, inputs, output_type="str")
    if response.startswith("```"):
        response = response[3:].strip()
    if response.startswith("markdown"):
        response = response[8:].strip()
    if response.endswith("```"):
        response = response[:-3].strip()

    await convert_to_pdf_for_lab(lab_id, response, "business", 1)
    

    # Replace the `idea_history` and `idea` fields
    lab["idea_history"] = [{
        "idea": response,
        "timestamp": datetime.datetime.now(),
        "version": 1.0
    }]
    lab["idea"] = response

    atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={
        "$set": {
            "status": "Idea Review",
            "idea_history": lab["idea_history"],
            "idea": lab["idea"]
        }
    })

    lab = _convert_object_ids_to_strings(lab)
    res = upload_file_to_github(lab_id, "idea.md", response, "Add concept lab idea.")
    return lab


async def generate_business_use_case_for_lab(lab_id: str, prompt, use_metaprompt=False):
    if use_metaprompt:
        prompt = _get_prompt("BUSINESS_USE_CASE_PROMPT")
        prompt = await generate_prompt(prompt)
    atlas_client = AtlasClient()

    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return "Lab not found"
    
    lab = lab[0]

    if prompt == "The request timed out. Please try again.":
        prompt = _get_prompt("BUSINESS_USE_CASE_PROMPT")

    idea_history = lab.get("idea_history")
    if not idea_history:
        return "Idea not found"
    
    idea = idea_history[-1].get("idea")
    
    inputs = {
        "NAME": lab.get("lab_name"),
        "DESCRIPTION": lab.get("lab_description"),
        "INSTRUCTIONS": idea
    }
    
    prompt = PromptTemplate(template=prompt, input_variables=inputs)

    llm = LLM("chatgpt")
    response = _get_response(llm, prompt, inputs, output_type="str")

    if response.startswith("```"):
        response = response[3:].strip()
    if response.startswith("markdown"):
        response = response[8:].strip()
    # if the response ends with ``` remove it
    if response.endswith("```"):
        response = response[:-3].strip()
        
    
    await convert_to_pdf_for_lab(lab_id, response, "business", 2)
    
    # Replace the `business_use_case_history` and `business` fields
    lab["business_use_case_history"] = [{
        "business_use_case": response,
        "timestamp": datetime.datetime.now(),
        "version": 1.0
    }]
    lab["business_use_case"] = response

    atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={
        "$set": {
            "status": "Business Use Case Review",
            "business_use_case_history": lab["business_use_case_history"],
            "business_use_case": response
        }
    })

    lab = _convert_object_ids_to_strings(lab)
    res = upload_file_to_github(lab_id, "business_requirements.md", response, "Add business requirements")
    return lab

async def generate_technical_specifications_for_lab(lab_id, prompt=_get_prompt("TECHNICAL_SPECIFICATION_PROMPT"), use_metaprompt=False):
    # if use_metaprompt:
    #     prompt = _get_prompt("TECHNICAL_SPECIFICATION_PROMPT")
    #     prompt = await generate_prompt(prompt)
    atlas_client = AtlasClient()

    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return "Lab not found"
    
    lab = lab[0]

    prompt = _get_prompt("TECHNICAL_SPECIFICATION_PROMPT")

    # if use_metaprrompt:
    #     prompt = await generate_prompt(prompt)

    if prompt == "The request timed out. Please try again.":
        prompt = _get_prompt("TECHNICAL_SPECIFICATION_PROMPT")


    idea = lab.get("selected_idea")
    if not idea:
        return "Selected Idea not found"
    
    idea_name = idea.get("name")
    idea_description = idea.get("description")
    
    
    inputs = {
        "NAME": idea_name,
        "DESCRIPTION": idea_description,
        "INSTRUCTIONS": _get_instructions_string(lab_id)
    }

    # Do this instead: Append the business use case to the prompt so that at frontend business use case parameters are not visible.
    prompt = PromptTemplate(template=prompt, input_variables=inputs)

    llm = LLM("chatgpt")
    response = _get_response(llm, prompt, inputs, output_type="str")

    if response.startswith("```"):
        response = response[3:].strip()
    if response.startswith("markdown"):
        response = response[8:].strip()
    # if the response ends with ``` remove it
    if response.endswith("```"):
        response = response[:-3].strip()

    await convert_to_pdf_for_lab(lab_id, response, "technical", 3)
    
    # Replace the `technical_specifications_history` and `technical_specifications` fields
    lab["technical_specifications_history"] = [{
        "technical_specifications": response,
        "timestamp": datetime.datetime.now(),
        "version": 1.0
    }]
    lab["technical_specifications"] = response

    atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={
        "$set": {
            "technical_specifications_history": lab["technical_specifications_history"],
            "technical_specifications": response,
            "status": "Technical Specifications",
        }
    })

    lab = _convert_object_ids_to_strings(lab)

    res = upload_file_to_github(lab_id, "technical_specifications.md", response, "Add technical specifications")
    return lab


async def regenerate_with_feedback(content, feedback, use_metaprompt=False):
    prompt = _get_prompt("REGENERATE_WITH_FEEDBACK_PROMPT")
    inputs = {
        "CONTENT": content,
        "FEEDBACK": feedback
    }

    if use_metaprompt:
        prompt = await generate_prompt(prompt)

    if prompt == "The request timed out. Please try again.":
        prompt = _get_prompt("REGENERATE_WITH_FEEDBACK_PROMPT")

    prompt = PromptTemplate(template=prompt, input_variables=inputs)

    llm = LLM("chatgpt")
    response = _get_response(llm, prompt, inputs, output_type="str")

    return response

async def save_concept_lab_idea(lab_id, idea):
    atlas_client = AtlasClient()

    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return "Lab not found"
    
    lab = lab[0]

    lab["idea"] = idea
    await convert_to_pdf_for_lab(lab_id, idea, "idea", 1)

    idea_history = lab.get("idea_history", [])

    if not idea_history:
        idea_history = [{
            "idea": idea,
            "timestamp": datetime.datetime.now(),
            "version": 1.0
        }]
    else:
        latest_version = idea_history[-1]
        new_version = {
            "idea": idea,
            "timestamp": datetime.datetime.now(),
            "version": latest_version.get("version") + 1.0
        }
        idea_history.append(new_version)

    atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={
        "$set": {
            "idea": idea,
            "idea_history": idea_history,
        }
    })

    lab = _convert_object_ids_to_strings(lab)
    res = update_file_in_github(
        repo_name=lab_id, 
        file_path="idea.md", 
        new_content=idea, 
        commit_message=f"Update Idea to {latest_version.get('version') + 1.0}"
    )
    return lab

async def save_business_use_case(lab_id, business_use_case):
    atlas_client = AtlasClient()

    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return "Lab not found"
    
    lab = lab[0]

    lab["business_use_case"] = business_use_case
    await convert_to_pdf_for_lab(lab_id, business_use_case, "business", 2)

    business_use_case_history = lab.get("business_use_case_history", [])

    if not business_use_case_history:
        business_use_case_history = [{
            "business_use_case": business_use_case,
            "timestamp": datetime.datetime.now(),
            "version": 1.0
        }]
    else:
        latest_version = business_use_case_history[-1]
        new_version = {
            "business_use_case": business_use_case,
            "timestamp": datetime.datetime.now(),
            "version": latest_version.get("version") + 1.0
        }
        business_use_case_history.append(new_version)

    atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={
        "$set": {
            "business_use_case": business_use_case,
            "business_use_case_history": business_use_case_history
        }
    })

    lab = _convert_object_ids_to_strings(lab)
    res = update_file_in_github(
        repo_name=lab_id, 
        file_path="business_requirements.md", 
        new_content=business_use_case, 
        commit_message=f"Update business requirements to {latest_version.get('version') + 1.0}"
    )
    return lab

async def save_technical_specifications(lab_id, technical_specifications):
    atlas_client = AtlasClient()

    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return "Lab not found"
    
    lab = lab[0]

    lab["technical_specifications"] = technical_specifications
    await convert_to_pdf_for_lab(lab_id, technical_specifications, "technical", 3)

    technical_specifications_history = lab.get("technical_specifications_history", [])

    if not technical_specifications_history:
        technical_specifications_history = [{
            "technical_specifications": technical_specifications,
            "timestamp": datetime.datetime.now(),
            "version": 1.0
        }]
    else:
        latest_version = technical_specifications_history[-1]
        new_version = {
            "technical_specifications": technical_specifications,
            "timestamp": datetime.datetime.now(),
            "version": latest_version.get("version") + 1.0
        }
        technical_specifications_history.append(new_version)

    atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={
        "$set": {
            "technical_specifications": technical_specifications,
            "technical_specifications_history": technical_specifications_history
        }
    })

    lab = _convert_object_ids_to_strings(lab)
    res = update_file_in_github(
        repo_name=lab_id, 
        file_path="technical_specifications.md", 
        new_content=technical_specifications, 
        commit_message=f"Update technical specifications to {latest_version.get('version') + 1.0}"
    )
    return lab


async def save_lab_instructions(lab_id, instructions):
    instructions = json.loads(instructions)
    atlas_client = AtlasClient()

    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return "Lab not found"
    
    lab = lab[0]

    lab["instructions"] = instructions

    atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={
        "$set": {
            "instructions": instructions
        }
    })

    lab = _convert_object_ids_to_strings(lab)

    return lab

async def submit_lab_for_generation(username, lab_id, company, model, key, queue_name_suffix, name, description, type, saveAPIKEY):
    print(f"username: {username}, lab_id: {lab_id}, model: {model}, key: {key}, queue_name_suffix: {queue_name_suffix}, name: {name}, saveAPIKEY: {saveAPIKEY}")
    atlas_client = AtlasClient()
    
    if saveAPIKEY:
            try: 
                await quAPIVault(username, company, model, key, name, description, type)
                # await _saveApiKey(username, company, model, key, type, name, description)
            except Exception as e:
                return f"An error occurred while saving API Key: {str(e)}"
            
    try:
        # Fetch the lab
        lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})
        if not lab:
            return "Lab not found"
        lab = lab[0]

        # Update the lab status
        queue_payload = {
            "lab_id": str(lab_id),
            "status": f"{queue_name_suffix.replace('_', ' ').title()}",
        }
        atlas_client.update("lab_design", {"_id": ObjectId(lab_id)}, {"$set": {"status": queue_payload["status"]}})

        # Check and update/insert into step directory
        existing_item = atlas_client.find(queue_name_suffix, {"lab_id": str(lab_id)}, limit=1)
        if existing_item:
            atlas_client.delete(queue_name_suffix, {"lab_id": str(lab_id)})
            atlas_client.insert(queue_name_suffix, {"lab_id": str(lab_id), "model": model, "key": key})
        else:
            atlas_client.insert(queue_name_suffix, {"lab_id": str(lab_id), "model": model, "key": key})

        # Convert ObjectId fields to strings
        lab = _convert_object_ids_to_strings(lab)
        return lab

    except Exception as e:
        return f"An error occurred: {str(e)}"
    

async def create_github_issue_in_lab(lab_id, issue_title, issue_description, labels, uploaded_files):
    if labels == ['']:
        labels = []
    if uploaded_files:
        s3_file_manager = S3FileManager()
        issue_description += "\n\n**Supporting Screenshots:**\n"
        for index, file in enumerate(uploaded_files):
            # Get file type
            resource_type = _get_file_type(file)

            # Define the S3 key
            key = f"qu-lab-design/{lab_id}/image_{index}.{file.filename.split('.')[-1]}"
            await s3_file_manager.upload_file_from_frontend(file, key)

            # URL encode the key for S3
            key = quote(key)
            resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}" 

            # Append the image to the description in Markdown format
            issue_description += f"[image-screenshot-{index}]({resource_link})\n"
            
    if labels:
        # Ensure labels are properly formatted
        if isinstance(labels, list) and len(labels) == 1 and isinstance(labels[0], str):
            # Split the single string in the list into multiple elements
            # labels = [label.strip() for label in labels[0].split(",")]
            labels = [label.strip().lower() for label in labels[0].split(",")] 

    atlas_client = AtlasClient()
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return {"status": 404, "message": "Lab not found"}
    
    lab = lab[0]
    
    # Call the function to create the GitHub issue
    res = create_github_issue(lab_id, issue_title, issue_description, labels)
    
    if res is None:
        return {"status": 400, "message": "Unable to create issue"}
    
    return res


async def get_labs_prompt(prompt_type):
    if prompt_type == "initial":
        return _get_prompt("CONCEPT_LAB_IDEA_PROMPT")
    elif prompt_type == "idea":
        return _get_prompt("BUSINESS_USE_CASE_PROMPT")
    elif prompt_type == "business":
        return _get_prompt("TECHNICAL_SPECIFICATION_PROMPT")
    return ""


async def update_lab_info(lab_id, lab_name, lab_description):
    atlas_client = AtlasClient()
    
    # Fetch the course from the database
    lab_data = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab_data:
        return "Lab not found"
    
    lab = lab_data[0]  # Assuming find() returns a list, get the first match
    
    update_payload = {
        "$set": {
            "lab_name": lab_name,
            "lab_description": lab_description
        }
    }

    # Perform the update operation
    update_response = atlas_client.update(
        "lab_design",  # Collection name
        filter = {"_id": ObjectId(lab_id)},  # Identify the correct lab
        update = update_payload
    )

    # Check if the update was successful
    if update_response:
        return "Lab information updated successfully"
    else:
        return "Failed to update lab information"
    
async def update_lab_tags(lab_id, tags):
    atlas_client = AtlasClient()
     # Check if tags contain a single empty string and convert it to an empty list
    if len(tags) == 1 and tags[0] == "":
        tags = []
    
    # Fetch the course from the database
    lab_data = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab_data:
        return "Lab not found"
    
    update_payload = {
        "$set": {
            "tags": tags
        }
    }

    # Perform the update operation
    update_response = atlas_client.update(
        "lab_design",  # Collection name
        filter = {"_id": ObjectId(lab_id)},  # Identify the correct lab
        update = update_payload
    )

    # Check if the update was successful
    if update_response:
        return "Lab information updated successfully"
    else:
        return "Failed to update lab information"


def _get_instructions_string(lab_id):
    atlas_client = AtlasClient()
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})
    if not lab:
        return ""
    lab = lab[0]
    instructions = lab.get("instructions", {})
    instructions_string = ""
    for key, value in instructions.items():
        if value!="" or value!=[] or value!=False:
            instructions_string += f"**{key}**: {value}\n"
    return instructions_string

async def get_lab_ideas(lab_id):
    """
    Retrieve lab ideas by performing the following steps:
      1. Fetch the lab from the database.
      2. Download files from the lab's raw_resources using s3_file_manager.
      3. Retrieve the prompt for generating lab ideas.
      4. Initialize the Google Gemini client and upload the downloaded files.
      5. Generate a response using the Gemini model.
      6. Parse and handle the model's response.
      7. Clean up the downloaded files.
      8. Return the parsed lab ideas.

    Args:
        lab_id (str): The unique identifier for the lab.

    Returns:
        list or str: A list of lab ideas if parsed successfully, or an error message string.
    """
    atlas_client = AtlasClient()
    s3_file_manager = S3FileManager()

    # 1. Fetch the lab object from the database
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})
    if not lab:
        return "Lab not found"
    lab = lab[0]

    # 2. Create a directory for downloading files from S3
    download_path = f"downloads/lab_design/{lab_id}"
    Path(download_path).mkdir(parents=True, exist_ok=True)

    # 3. Initialize the Google Gemini client for file upload and model inference
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    uploaded_files = []

    # 4. Iterate through raw_resources, download each file from S3, and upload to Gemini
    raw_resources = lab.get("raw_resources", [])
    print(raw_resources)
    for resource in raw_resources:
        resource_link = resource.get("resource_link")
        # Construct the S3 key from the resource link
        key = f"qu-lab-design/{resource_link.split('qu-lab-design/')[1]}"
        download_file_path = f"{download_path}/{resource_link.split('/')[-1]}"
        s3_file_manager.download_file(key, download_file_path)
        
        # Upload the file to Gemini and store the resulting file reference
        uploaded_files.append(client.files.upload(file=download_file_path))
    
    # 5. Retrieve the prompt template for generating lab ideas
    prompt = _get_prompt("GENERATE_LAB_IDEAS")
    prompt = prompt.format(INSTRUCTIONS=_get_instructions_string(lab_id))

    # 6. Generate content by combining the prompt with the uploaded files using the Gemini model
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL"),
        contents=[prompt] + uploaded_files
    )
    response = response.text
    logging.info(response)
    
    # 7. Attempt to extract and parse the JSON part of the response
    try:
        response = response[response.index("```json") + 7:response.rindex("```")].strip()
        response = json.loads(response)
        response.append({
            "name": "Custom",
            "description": "Describe your custom lab here."
        })
    except Exception as e:
        logging.error(e)
        # Fallback sample lab ideas in case of an error during parsing
        response = [
            {
                "name": "Compound Interest Visualizer",
                "description": "### Overview\nCreate a **one-page** Streamlit app that demonstrates the power of compound interest. Users can input their principal amount, annual interest rate, and investment duration. The app will:\n\n- **Calculate Future Value**: Show how the investment grows over time with monthly or annual compounding.\n- **Interactive Chart**: Display a line chart comparing simple interest vs. compound interest growth.\n\n### How It Explains the Concept\nBy visualizing the differences in growth, users learn how compound interest accumulates earnings not just on the principal but also on previous interest, making it a cornerstone concept in **long-term investing**."
            },
            {
                "name": "Mortgage Calculator with Amortization Breakdown",
                "description": "### Overview\nDesign a **one-page** Streamlit app to calculate monthly mortgage payments and illustrate the amortization schedule. Users input:\n\n- **Loan Amount**\n- **Interest Rate**\n- **Loan Term** (in years)\n\n### Features\n- **Payment Calculation**: Automatically computes monthly payments.\n- **Amortization Chart**: Shows how each payment splits between principal and interest over time.\n\n### How It Explains the Concept\nThe app helps users understand **amortization**—the process of gradually paying off debt through regular payments that cover both interest and principal. Visual cues make it clear how interest is front-loaded in the early years of a mortgage."
            },
            {
                "name": "Stock Portfolio Tracker with Risk Assessment",
                "description": "### Overview\nDevelop a **one-page** Streamlit app that allows users to track their stock holdings and see simple risk metrics. Users can:\n\n- **Add or Remove Stocks**: Enter ticker symbols and the number of shares.\n- **Fetch Real-Time Data**: Pull current prices from a public API.\n- **Portfolio Allocation**: Show a pie chart of holdings by market value.\n\n### Features\n- **Volatility Gauge**: Calculate and display standard deviation or beta for each stock.\n- **Performance Trends**: Display a line chart of portfolio value over time.\n\n### How It Explains the Concept\nBy breaking down **risk assessment** (like volatility) in a user-friendly manner, the app helps users grasp how stock performance fluctuations can impact overall portfolio stability. It provides a practical introduction to risk management concepts in investing."
            },
            {
                "name": "Budget vs. Actual Spending Dashboard",
                "description": "### Overview\nCreate a **one-page** Streamlit app that compares a user's budgeted spending to their actual expenses. Users can:\n\n- **Input Budget Categories**: e.g., Rent, Groceries, Entertainment.\n- **Log Actual Expenses**: Enter real spending amounts throughout the month.\n- **View Summaries**: Display a bar chart or gauge showing the difference between budgeted vs. actual amounts.\n\n### Features\n- **Alerts**: Highlight overspending in red.\n- **Trend Analysis**: Show a mini line chart for each category over time.\n\n### How It Explains the Concept\nThis dashboard clarifies **budgeting**—the practice of planning income and expenses in advance. By contrasting expected vs. real spending, users see how well they stick to their financial goals, reinforcing the importance of proactive money management."
            }
        ]

    # 8. Clean up by removing the download directory and its contents
    shutil.rmtree(download_path)

    # 9. Add the lab ideas to the lab object and update the database
    lab["lab_ideas"] = response
    atlas_client.update(
        "lab_design",
        filter={"_id": ObjectId(lab_id)},
        update={"$set": {"lab_ideas": response, "status": "Idea Selection"}}
    )

    # Return the parsed lab ideas
    return response

async def update_lab_ideas(lab_id, lab_ideas):
    """
    Asynchronously updates the 'lab_ideas' field of a lab design document.

    This function retrieves a lab design document from the database using the provided lab_id.
    If the lab is found, its 'lab_ideas' field is updated with the given value using an update
    operation. The function then converts any MongoDB ObjectIds in the document to strings before
    returning it. If no lab is found with the specified lab_id, a "Lab not found" message is returned.

    Args:
        lab_id: A unique identifier for the lab document, expected to be convertible to an ObjectId.
        lab_ideas: The new data to update the 'lab_ideas' field of the lab design.

    Returns:
        The updated lab design document with ObjectIds converted to strings, or a string message
        "Lab not found" if the lab document does not exist.
    """
    atlas_client = AtlasClient()
    lab_ideas = json.loads(lab_ideas)
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})
    if not lab:
        return "Lab not found"
    lab = lab[0]
    lab["lab_ideas"] = lab_ideas
    atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={"$set": {"lab_ideas": lab_ideas}})

    lab = _convert_object_ids_to_strings(lab)
    return lab

async def update_selected_idea(lab_id, index):
    """
    Update the selected idea of a lab design entry in the database.
    This function retrieves a lab design using the provided lab_id, updates its "selected_idea" field by selecting an idea
    from the lab's "lab_ideas" list based on the given index, and returns the updated lab design. ObjectIds in the lab design
    are converted to their string representations using a helper function before returning.
    Parameters:
        lab_id (str): The unique identifier of the lab design to be updated.
        index (int): The index of the desired idea in the lab's "lab_ideas" list to set as the selected idea.
    Returns:
        dict or str: The updated lab design with ObjectIds converted to strings if the lab is found,
                     otherwise returns "Lab not found".
    """
    # Initialize the AtlasClient for database operations
    atlas_client = AtlasClient()

    # Retrieve the lab design document using the provided lab_id
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    # If the lab is not found, return an error message
    if not lab:
        return "Lab not found"
    
    # Extract the first lab design document from the result
    lab = lab[0]
    # Get the list of lab ideas; default to an empty list if not present
    lab_ideas = lab.get("lab_ideas", [])

    # Update the lab design document by setting the selected idea based on the provided index
    atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={
        "$set": {
            "selected_idea": lab_ideas[index]
        }
    })

    # Convert any ObjectId fields in the lab document to strings for compatibility
    lab['selected_idea'] = lab_ideas[index]
    lab = _convert_object_ids_to_strings(lab)

    # Return the updated lab design document
    return lab


async def update_lab_design_status(lab_id, lab_design_status):
    print(lab_id, lab_design_status)
    atlas_client = AtlasClient()

    # Retrieve the lab design document using the provided lab_id
    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    # If the lab is not found, return an error message
    if not lab:
        return "Lab not found"

    # Extract the first lab design document from the result
    lab = lab[0]
    
    # Update the lab design document by setting the status based on the provided lab_design_status
    response = atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={
        "$set": {
            "status": lab_design_status
        }
    })
    
    # Check if the update was successful
    if response:
        return "Lab status updated successfully"
    else:
        return "Failed to update lab status"

async def validate_key(model, key):
    print("Model ID: ", model)
    print("API Key: ", key)
    print("Response: ", check_valid_key(model, key))
    return check_valid_key(model, key)