
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


LECTURE_DESIGN_STEPS = [
    "raw_resources", #automatic
    "in_content_generation_queue", #automatic
    "pre_processed_content", #expert-review-step
    "post_processed_content", #automatic
    "in_structure_generation_queue", #automatic
    "pre_processed_structure", #expert-review-step
    "post_processed_structure", #automatic
    "in_deliverables_generation_queue", #automatic
    "pre_processed_deliverables", #expert-review-step
    "post_processed_deliverables", #automatic
]


def _get_lecture(lecture_id):
    atlas_client = AtlasClient()
    lecture = atlas_client.find("lecture_design", filter={"_id": ObjectId(lecture_id)})
    if not lecture:
        return "Lecture not found", None
    
    lecture = lecture[0]
    
    return lecture, None

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

async def get_lectures():
    atlas_client = AtlasClient()
    lectures = atlas_client.find("lecture_design")
    lectures = _convert_object_ids_to_strings(lectures)
    return lectures
    
# generate_course_outline -> take in the input as the file and the instructions and generate the course outline
async def generate_lecture_outline(files, instructions):

    lecture_outline_instructions = _get_prompt("LECTURE_OUTLINE_PROMPT")
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
            instructions=lecture_outline_instructions,
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
                "content": "Create the lecture outline based on the instructions provided and the following user's instructions: " + instructions,
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
        logging.error(f"Error in generating lecture outline: {e}")
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
async def clone_lecture(lecture_id):
    
    atlas_client = AtlasClient()
    lecture = atlas_client.find("lecture_design", filter={"_id": ObjectId(lecture_id)})

    if not lecture:
        return "Lecture not found"
    
    lecture = lecture[0]
    lecture.pop("_id")

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

    atlas_client.insert("lecture_design", lecture)

    lecture = _convert_object_ids_to_strings(lecture)

    return lecture


# delete_course -> takes in the course_id and deletes the course
async def delete_lecture(lecture_id):
    
    atlas_client = AtlasClient()
    lecture = atlas_client.find("lecture_design", filter={"_id": ObjectId(lecture_id)})

    if not lecture:
        return "Lecture not found"
    
    lecture = lecture[0]
    
    atlas_client.delete("lecture_design", filter={"_id": ObjectId(lecture_id)})

    lecture = _convert_object_ids_to_strings(lecture)
    
    return lecture
    

# create_course -> takes in the course name, course image, course description, files, course_outline, and creates a course object. also handles creation of modules
async def create_lecture(lecture_name, lecture_description, lecture_outline, files, lecture_image):
    lecture_status = "In Design Phase"

    s3_file_manager = S3FileManager()
    atlas_client = AtlasClient()

    
    # upload the course image to s3 and get the link
    lecture_id = ObjectId()
    key = f"qu-lecture-design/{lecture_id}/lecture_image/{lecture_image.filename}"
    await s3_file_manager.upload_file_from_frontend(lecture_image, key)
    key = quote(key)
    lecture_image_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"


    lecture = {
        "_id": lecture_id,
        "lecture_name": lecture_name,
        "lecture_description": lecture_description,
        "lecture_image": lecture_image_link,
        "lecture_outline": lecture_outline,
        "status": lecture_status
    }
    step_directory = LECTURE_DESIGN_STEPS[0]


    raw_resources = []
    if files:
        for file in files:
            resource_type = _get_file_type(file)

            key = f"qu-lecture-design/{lecture_id}/{step_directory}/{file.filename}"  
            await s3_file_manager.upload_file_from_frontend(file, key)
            key = quote(key)
            resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"    
                
            raw_resources += [{
                "resource_id": ObjectId(),
                "resource_type": resource_type,
                "resource_name": file.filename,
                "resource_description": "",
                "resource_link": resource_link
            }]
    
    lecture[step_directory] = raw_resources

    atlas_client.insert("lecture_design", lecture)

    lecture = _convert_object_ids_to_strings(lecture)
    return lecture


def _get_resource_key_from_link(resource_link):
    resource_prefix = resource_link.split("aws.com/")[1]
    # unquote the key
    resource_key = unquote(resource_prefix)
    return resource_key


# get_course -> takes in the course_id and returns the course object
async def get_lecture(lecture_id):

    atlas_client = AtlasClient()
    lecture = atlas_client.find("lecture_design", filter={"_id": ObjectId(lecture_id)})

    if not lecture:
        return {}
    
    lecture = lecture[0]
    lecture = _convert_object_ids_to_strings(lecture)
    
    return lecture

# add_resources_to_module -> takes in the lecture_id, resource_type, resource_name, resource_description, resource_file, and adds a resource to the module and to s3
async def add_resources_to_lecture(lecture_id, resource_type, resource_name, resource_description, resource_file, resource_id=None, lecture_design_step=0):
    s3_file_manager = S3FileManager()
    step_directory = LECTURE_DESIGN_STEPS[lecture_design_step]
    resource_id = ObjectId() if not resource_id else ObjectId(resource_id)

    if resource_type in {"File", "Assessment", "Image", "Slide_Generated", "Slide_Content", "Video"}:
        # resource file is the file
        key = f"qu-lecture-design/{lecture_id}/{step_directory}/{str(resource_id)}."+resource_file.filename.split(".")[-1]
        await s3_file_manager.upload_file_from_frontend(resource_file, key)
        key = quote(key)
        resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

    elif resource_type == "Image":
        # resource file is the image
        key = f"qu-lecture-design/{lecture_id}/{step_directory}/{str(resource_id)}."+resource_file.filename.split(".")[-1]
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

        key = f"qu-lecture-design/{lecture_id}/{step_directory}/{resource_file_name}"
        await s3_file_manager.upload_file(resource_file_name, key)
        key = quote(key)

        # remove the temp file
        os.remove(resource_file_name)
        resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

    atlas_client = AtlasClient()
    lecture = atlas_client.find("lecture_design", filter={"_id": ObjectId(lecture_id)})
    if not lecture:
        return "lecture not found"
    
    lecture = lecture[0]
    resources = lecture.get(step_directory, [])
    resource = {
        "resource_id": resource_id,
        "resource_type": resource_type,
        "resource_name": resource_name,
        "resource_description": resource_description,
        "resource_link": resource_link
    }
    resources.append(resource)
    lecture[step_directory] = resources

    atlas_client.update("lecture_design", filter={"_id": ObjectId(lecture_id)}, update={
        "$set": {
            step_directory: resources
        }
    }
    )

    lecture = _convert_object_ids_to_strings(lecture)

    return lecture


# delete_resource_from_module -> takes in the course_id, module_id, resource_id, and deletes the resource from the module and from s3
async def delete_resources_from_lecture(lecture_id, resource_id, lecture_design_step=0):
    step_directory = LECTURE_DESIGN_STEPS[lecture_design_step]

    atlas_client = AtlasClient()
    lecture = atlas_client.find("lecture_design", filter={"_id": ObjectId(lecture_id)})

    if not lecture:
        return "Lecture not found"
    
    lecture = lecture[0]
    resources = lecture.get(step_directory, [])
    for resource in resources:
        if resource.get("resource_id") == ObjectId(resource_id):
            resources.remove(resource)
            break
    

    atlas_client.update("lecture_design", filter={"_id": ObjectId(lecture_id)}, update={
        "$set": {
            step_directory: resources
        }
    }
    )

    lecture = _convert_object_ids_to_strings(lecture)

    return lecture

# replace the resource in the module and s3
async def replace_resources_in_lecture(lecture_id, resource_id, resource_name, resource_type, resource_description, resource_file, lecture_design_step=0):
    
    # delete the resource with the resource id, and add the new resource with the same id
    lecture = await delete_resources_from_lecture(lecture_id=lecture_id,
                                                resource_id=resource_id, 
                                                lecture_design_step=lecture_design_step)

    # add the new resource
    lecture = await add_resources_to_lecture(lecture_id=lecture_id,
                                           resource_type=resource_type, 
                                           resource_name=resource_name, 
                                           resource_description=resource_description, 
                                           resource_file=resource_file, 
                                           resource_id=resource_id, 
                                           lecture_design_step=lecture_design_step)

    lecture = _convert_object_ids_to_strings(lecture)
    
    return lecture

def _handle_s3_file_transfer(lecture_id, prev_step_directory, step_directory, resources):
    s3_file_manager = S3FileManager()
    for resource in resources:
        next_step_key = f"qu-lecture-design/{lecture_id}/{step_directory}/{resource.get('resource_name')}"
        prev_step_key = f"qu-lecture-design/{lecture_id}/{prev_step_directory}/{resource.get('resource_name')}"
        s3_file_manager.copy_file(prev_step_key, next_step_key)

async def submit_lecture_for_step(lecture_id, lecture_design_step, queue_name_suffix, instructions=""):
    step_directory = LECTURE_DESIGN_STEPS[lecture_design_step]
    prev_step_directory = LECTURE_DESIGN_STEPS[lecture_design_step - 1]

    lecture, _ = _get_lecture(lecture_id=lecture_id)

    if not lecture:
        return "Lecture not found"

    lecture["status"] = f"{queue_name_suffix.replace('_', ' ').title()}"
    if instructions:
        lecture["instructions"] = instructions

    atlas_client = AtlasClient()
    atlas_client.update("lecture_design", filter={"_id": ObjectId(lecture_id)}, update={
        "$set": {
            "status": f"{queue_name_suffix.replace('_', ' ').title()}"
        }
    })

    prev_step_resources = lecture.get(prev_step_directory, [])
    _handle_s3_file_transfer(lecture_id, prev_step_directory, step_directory, prev_step_resources)

    queue_payload = {
        "lecture_id": lecture_id,
        "type": "lecture"
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

    
