from app.services.report_generation.generate_pdf import convert_markdown_to_pdf
import datetime
import mimetypes
import requests
from fastapi import HTTPException
from urllib.parse import urlparse
from app.utils.llm import LLM
from app.utils.s3_file_manager import S3FileManager
from app.utils.atlas_client import AtlasClient
import logging
import time
import random
import json
import ast
from bson.objectid import ObjectId
from openai import OpenAI
import os
from fastapi import UploadFile
from urllib.parse import quote, unquote
from langchain_core.prompts import PromptTemplate


LAB_DESIGN_STEPS = [
    "raw_resources", #automatic
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

async def get_labs():
    atlas_client = AtlasClient()
    labs = atlas_client.find("lab_design")
    labs = _convert_object_ids_to_strings(labs)
    return labs
    
# generate_course_outline -> take in the input as the file and the instructions and generate the course outline
async def generate_lab_outline(files, instructions):

    lab_outline_instructions = _get_prompt("LAB_OUTLINE_PROMPT")
    client = OpenAI(api_key=os.getenv("OPENAI_KEY"))

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
                "content": "Create the lab outline based on the instructions provided and the following user's instructions: " + instructions,
            }]
        )
        created_thread_id = thread.id  # Track the thread

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id, assistant_id=assistant.id
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
        return "# Slide 1: **On Machine Learning Applications in Investments**\n**Description**: This module provides an overview of the use of machine learning (ML) in investment practices, including its potential benefits and common challenges. It highlights examples where ML techniques have outperformed traditional investment models.\n\n**Learning Outcomes**:\n- Understand the motivations behind using ML in investment strategies.\n- Recognize the challenges and solutions in applying ML to finance.\n- Explore practical applications of ML for predicting equity returns and corporate performance.\n### Slide 2: **Alternative Data and AI in Investment Research**\n**Description**: This module explores how alternative data sources combined with AI are transforming investment research by providing unique insights and augmenting traditional methods.\n\n**Learning Outcomes**:\n- Identify key sources of alternative data and their relevance in investment research.\n- Understand how AI can process and derive actionable insights from alternative data.\n- Analyze real-world use cases showcasing the impact of AI in research and decision-making.\n### Slide 3: **Data Science for Active and Long-Term Fundamental Investing**\n**Description**: This module covers the integration of data science into long-term fundamental investing, discussing how quantitative analysis can enhance traditional methods.\n\n**Learning Outcomes**:\n- Learn the foundational role of data science in long-term investment strategies.\n- Understand the benefits of combining data science with active investing.\n- Evaluate case studies on the effective use of data science to support investment decisions.\n### Slide 4: **Unlocking Insights and Opportunities**\n**Description**: This module focuses on techniques and strategies for using data-driven insights to identify market opportunities and enhance investment management processes.\n\n**Learning Outcomes**:\n- Grasp the importance of leveraging advanced data analytics for opportunity identification.\n- Understand how to apply insights derived from data to optimize investment outcomes.\n- Explore tools and methodologies that facilitate the unlocking of valuable investment insights.\n### Slide 5: **Advances in Natural Language Understanding for Investment Management**\n**Description**: This module highlights the progression of natural language understanding (NLU) and its application in finance. It covers recent developments and their implications for asset management.\n\n**Learning Outcomes**:\n- Recognize advancements in NLU and their integration into investment strategies.\n- Explore trends and applications of NLU in financial data analysis.\n- Understand the technical challenges and solutions associated with implementing NLU tools.\n###"
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
    
    atlas_client.delete("lab_design", filter={"_id": ObjectId(lab_id)})

    lab = _convert_object_ids_to_strings(lab)
    
    return lab
    

# create_course -> takes in the course name, course image, course description, files, course_outline, and creates a course object. also handles creation of modules
async def create_lab(lab_name, lab_description, lab_outline, files, lab_image):
    lab_status = "In Design Phase"

    s3_file_manager = S3FileManager()
    atlas_client = AtlasClient()

    
    # upload the course image to s3 and get the link
    lab_id = ObjectId()
    key = f"qu-lab-design/{lab_id}/lab_image/{lab_image.filename}"
    await s3_file_manager.upload_file_from_frontend(lab_image, key)
    key = quote(key)
    lab_image_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"


    lab = {
        "_id": lab_id,
        "lab_name": lab_name,
        "lab_description": lab_description,
        "lab_image": lab_image_link,
        "lab_outline": lab_outline,
        "status": lab_status,
        "instructions": {
            "learningOutcomes": "",
            "responsive": False,
            "datasetType": "",
            "links": [],
            "datasetFile": [],
            "visualizations": "",
            "frameworks": "",
            "accessibility": "",
            "exportFormats": "",
            "visualReferences": [],
            "documentation": False,
        }
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

    if resource_type in {"File", "Assessment", "Image", "Slide_Generated", "Slide_Content", "Video"}:
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
    
async def generate_business_use_case_for_lab(lab_id: str, instructions: str):
    atlas_client = AtlasClient()

    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return "Lab not found"
    
    lab = lab[0]

    prompt = _get_prompt("BUSINESS_USE_CASE_PROMPT")

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

    if not lab.get("business_use_case_history"):
        lab["business_use_case_history"] = [{
            "business_use_case": response,
            "timestamp": datetime.datetime.now(),
            "version": 1.0
        }]
    else:
        latest_version = lab["business_use_case_history"][-1]
        new_version = {
            "business_use_case": response,
            "timestamp": datetime.datetime.now(),
            "version": latest_version.get("version") + 1.0
        }
        lab["business_use_case_history"].append(new_version)

    atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={
        "$set": {
            "status": "Business Use Case Review",
            "business_use_case_history": lab["business_use_case_history"],
            "business_use_case": response
        }
    })

    lab = _convert_object_ids_to_strings(lab)
    return lab

async def generate_technical_specifications_for_lab(lab_id):
    atlas_client = AtlasClient()

    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return "Lab not found"
    
    lab = lab[0]

    prompt = _get_prompt("TECHNICAL_SPECIFICATION_PROMPT")


    business_use_case_history = lab.get("business_use_case_history")
    if not business_use_case_history:
        return "Business use case not found"
    
    business_use_case = business_use_case_history[-1].get("business_use_case")
    
    inputs = {
        "BUSINESS_USE_CASE": business_use_case
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

    lab["technical_specifications"] = response

    await convert_to_pdf_for_lab(lab_id, response, "technical", 2)

    if not lab.get("technical_specifications_history"):
        lab["technical_specifications_history"] = [{
            "technical_specifications": response,
            "timestamp": datetime.datetime.now(),
            "version": 1.0
        }]
    else:
        latest_version = lab["technical_specifications_history"][-1]
        new_version = {
            "technical_specifications": response,
            "timestamp": datetime.datetime.now(),
            "version": latest_version.get("version") + 1.0
        }
        lab["technical_specifications_history"].append(new_version)

    atlas_client.update("lab_design", filter={"_id": ObjectId(lab_id)}, update={
        "$set": {
            "status": "Technical Specifications Review",
            "technical_specifications_history": lab["technical_specifications_history"],
            "technical_specifications": response
        }
    })

    lab = _convert_object_ids_to_strings(lab)

    return lab


async def regenerate_with_feedback(content, feedback):
    prompt = _get_prompt("REGENERATE_WITH_FEEDBACK_PROMPT")
    inputs = {
        "CONTENT": content,
        "FEEDBACK": feedback
    }

    prompt = PromptTemplate(template=prompt, input_variables=inputs)

    llm = LLM("chatgpt")
    response = _get_response(llm, prompt, inputs, output_type="str")

    return response

async def save_business_use_case(lab_id, business_use_case):
    atlas_client = AtlasClient()

    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return "Lab not found"
    
    lab = lab[0]

    lab["business_use_case"] = business_use_case
    await convert_to_pdf_for_lab(lab_id, business_use_case, "business", 1)

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

    return lab

async def save_technical_specifications(lab_id, technical_specifications):
    atlas_client = AtlasClient()

    lab = atlas_client.find("lab_design", filter={"_id": ObjectId(lab_id)})

    if not lab:
        return "Lab not found"
    
    lab = lab[0]

    lab["technical_specifications"] = technical_specifications
    await convert_to_pdf_for_lab(lab_id, technical_specifications, "technical", 2)

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