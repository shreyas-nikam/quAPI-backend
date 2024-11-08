# generate_course_outline, clone_course, delete_course, create_course, add_module, add_resources_to_module, get_course, submit_module_for_content_generation, save_changes_post_content_generation, submit_module_for_structure_generation, save_changes_post_structure_generation, submit_module_for_deliverables_generation, save_changes_post_deliverables_generation, submit_for_publishing_pipeline
# the stages of the course design pipeline are: raw_resources, in_content_generation_queue, pre_processed_content, post_processed_content, in_structure_generation_queue, pre_processed_structure, post_processed_structure, in_deliverables_generation_queue, pre_processed_deliverables, post_processed_deliverables, in_publishing_queue, published
from app.utils.llm import LLM
from app.utils.s3_file_manager import S3FileManager
from app.utils.atlas_client import AtlasClient
import logging
import time
import random
import json
import ast
from langchain_core.prompts import PromptTemplate
from bson.objectid import ObjectId
from openai import OpenAI
import os
from fastapi import UploadFile
from urllib.parse import quote


COURSE_DESIGN_STEPS = [
    "raw_resources", #automatic
    "in_content_generation_queue", #automatic
    "pre_processed_content", #manual
    "post_processed_content", #automatic
    "in_structure_generation_queue", #automatic
    "pre_processed_structure", #manual
    "post_processed_structure", #automatic
    "in_deliverables_generation_queue", #automatic
    "pre_processed_deliverables", #manual
    "post_processed_deliverables", #automatic
    "in_publishing_queue", #automatic
    "published" #manual
]


def _get_course_and_module(course_id, module_id):
    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})
    if not course:
        return "Course not found", None
    
    course = course[0]
    module = next((m for m in course.get("modules", []) if m.get("_id") == ObjectId(module_id)), None)
    if not module:
        return None, "Module not found"
    
    return course, module

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
        return "image"
    elif file.content_type.startswith("text"):
        return "note"
    else:
        return "file"

async def get_courses():
    atlas_client = AtlasClient()
    courses = atlas_client.find("course_design")
    courses = _convert_object_ids_to_strings(courses)
    return courses
    
# generate_course_outline -> take in the input as the file and the instructions and generate the course outline
async def generate_course_outline(files, instructions):

    course_outline_instructions = _get_prompt("COURSE_OUTLINE_PROMPT")
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
            name="Course outline creator",
            instructions=course_outline_instructions,
            model=os.getenv("OPENAI_MODEL"),
            tools=[{"type": "file_search"}]
        )
        created_assistant_id = assistant.id  # Track the assistant

        vector_store = client.beta.vector_stores.create(
            name="Course Resources",
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
                "content": "Create the course outline based on the instructions provided and the following user's instructions: " + instructions,
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
async def clone_course(course_id):
    
    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})

    if not course:
        return "Course not found"
    
    course = course[0]
    course.pop("_id")

    new_course = course.copy()
    
    new_course_id = atlas_client.insert("course_design", new_course)

    new_course = _convert_object_ids_to_strings(new_course)
    
    return new_course

# delete_course -> takes in the course_id and deletes the course
async def delete_course(course_id):
    
    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})

    if not course:
        return "Course not found"
    
    course = course[0]
    
    atlas_client.delete("course_design", filter={"_id": ObjectId(course_id)})

    course = _convert_object_ids_to_strings(course)
    
    return course
    

# create_course -> takes in the course name, course image, course description, files, course_outline, and creates a course object. also handles creation of modules
async def create_course(course_name, course_description, course_outline, files, course_image):


    course_status = "In Design"


    s3_file_manager = S3FileManager()
    
    atlas_client = AtlasClient()

    # convert the course outline to modules
    course_outline_to_modules_prompt = _get_prompt("COURSE_OUTLINE_TO_MODULES_PROMPT")
    inputs = {
        "COURSE_OUTLINE": course_outline
    }
    prompt = PromptTemplate(template=course_outline_to_modules_prompt, 
                            input_variables = ["COURSE_OUTLINE"])
    
    llm = LLM("chatgpt")
    response = _get_response(llm, prompt, inputs, output_type="json")


    # upload the course image to s3 and get the link
    course_id = ObjectId()
    key = f"qu-course-design/{course_id}/course_image/{course_image.filename}"
    await s3_file_manager.upload_file_from_frontend(course_image, key)
    key = quote(key)
    course_image_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"


    course = {
        "_id": course_id,
        "course_name": course_name,
        "course_description": course_description,
        "course_image": course_image_link,
        "course_outline": course_outline,
        "status": course_status
    }

    step_directory = COURSE_DESIGN_STEPS[0]


    modules = response.get("modules", []) 

    
    for index, module in enumerate(modules):
        module_id = ObjectId()
        modules[index]["module_id"] = module_id

        raw_resources = []

        for file in files:
            resource_type = _get_file_type(file)

            key = f"qu-course-design/{course_id}/{str(module_id)}/{step_directory}/{file.filename}"  
            await s3_file_manager.upload_file_from_frontend(file, key)
            key = quote(key)
            resource_link = f"https://qucoursify.s3.amazonaws.com/{key}"    
                
            raw_resources += [{
                "resource_id": ObjectId(),
                "resource_type": resource_type,
                "resource_name": file.filename,
                "resource_description": "",
                "resource_link": resource_link
            }]
        
        modules[index][step_directory] = raw_resources

    course["modules"] = modules

    atlas_client.insert("course_design", course)

    course = _convert_object_ids_to_strings(course)
    return course

# add_module -> takes in the course_id, module_name, module_description, and adds a module to the course
async def add_module(payload):
    course_id = payload['course_id']
    module_name = payload['module_name']
    module_description = payload['module_description']

    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})

    if not course:
        return "Course not found"
    
    course = course[0]
    modules = course.get("modules", [])
    module = {
        "module_id": ObjectId(),
        "module_name": module_name,
        "module_description": module_description,
        "status": "Not Submitted"
    }
    modules.append(module)
    course["modules"] = modules

    # add all files as resources to modules
    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={
        "$set": {
            "modules": modules
        }
    })

    return course

# get_course -> takes in the course_id and returns the course object
async def get_course(payload):
    course_id = payload['course_id']

    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})

    if not course:
        return {}
    
    return course[0]

# add_resources_to_module -> takes in the course_id, module_id, resource_type, resource_name, resource_description, resource_file, and adds a resource to the module and to s3
async def add_resources_to_module(payload, resource_id=""):
    course_id = payload['course_id']
    module_id = payload['module_id']
    resource_type = payload['resource_type']
    resource_name = payload['resource_name']
    resource_description = payload['resource_description']
    resource_file = payload['resource_file']
    s3_file_manager = S3FileManager()
    course_design_step = 0
    step_directory = COURSE_DESIGN_STEPS[course_design_step]

    # if resource_type is file, then upload the file to s3 and get the link
    # if resource type is link, then use the link as the resource link
    # if the resource type is note, the write it in an md file and upload it to s3 and get the link
    # if the resource_type is an image, then upload the image to s3 and get the link
    if(resource_type == "file"):
        key = f"qu-course-design/{course_id}/{module_id}/{step_directory}/{resource_file}"
        s3_file_manager.upload_file_obj(resource_file, key)
        resource_link = f"https://qucoursify.s3.amazonaws.com/{key}"

    elif(resource_type == "link"):
        resource_link = resource_file

    elif(resource_type == "note"):
        s3_file_manager = S3FileManager()
        # create a temp md file with the resource description as the content
        resource_file = resource_file + ".md"
        with open(resource_file, "w") as file:
            file.write(resource_description)

        key = f"qu-course-design/{course_id}/{module_id}/{step_directory}/{resource_file}"
        s3_file_manager.upload_file_obj(resource_file, key)
        resource_link = f"https://qucoursify.s3.amazonaws.com/{key}"


    elif(resource_type == "image"):
        key = f"qu-course-design/{course_id}/{module_id}/{step_directory}/{resource_file}"
        s3_file_manager.upload_file_obj(resource_file, key)
        resource_link = f"https://qucoursify.s3.amazonaws.com/{key}"


    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})
    if not course:
        return "Course not found"
    
    course = course[0]
    modules = course.get("modules", [])

    for module in modules:
        if module.get("_id") == ObjectId(module_id):
            resources = module.get(f"{step_directory}", [])
            resource = {
                "resource_id": ObjectId() if not resource_id else ObjectId(resource_id),
                "resource_type": resource_type,
                "resource_name": resource_name,
                "resource_description": resource_description,
                "resource_link": resource_link
            }
            resources.append(resource)
            module[f"{step_directory}"] = resources
            break

    course["modules"] = modules

    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={
        "$set": {
            "modules": modules
        }
    }
    )

    return course


# delete_resource_from_module -> takes in the course_id, module_id, resource_id, and deletes the resource from the module and from s3
async def delete_resource_from_module(payload):
    course_id = payload['course_id']
    module_id = payload['module_id']
    resource_id = payload['resource_id']
    course_design_step = 0
    step_directory = COURSE_DESIGN_STEPS[course_design_step]

    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})

    if not course:
        return "Course not found"
    
    course = course[0]
    modules = course.get("modules", [])
    for module in modules:
        if module.get("_id") == ObjectId(module_id):
            resources = module.get(step_directory, [])
            for resource in resources:
                if resource.get("_id") == ObjectId(resource_id):
                    resources.remove(resource)
                    break
            module[step_directory] = resources
            break
    
    course["modules"] = modules

    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={
        "$set": {
            "modules": modules
        }
    }
    )

    return course


async def replace_resources_in_module(payload):
    resource_id = payload['resource_id']

    # delete the resource with the resource id, and add the new resource with the same id
    delete_resource_from_module(payload)

    # add the new resource
    add_resources_to_module(payload, resource_id)

def _handle_s3_file_transfer(course_id, module_id, prev_step_directory, step_directory, resources):
    s3_file_manager = S3FileManager()
    for resource in resources:
        next_step_key = f"qu-course-design/{course_id}/{module_id}/{step_directory}/{resource.get('resource_name')}"
        prev_step_key = f"qu-course-design/{course_id}/{module_id}/{prev_step_directory}/{resource.get('resource_name')}"
        s3_file_manager.copy_file(prev_step_key, next_step_key)

async def submit_module_for_step(payload, course_design_step, queue_name_suffix):
    course_id = payload['course_id']
    module_id = payload['module_id']
    instructions = payload.get("instructions", "")
    step_directory = COURSE_DESIGN_STEPS[course_design_step]
    prev_step_directory = COURSE_DESIGN_STEPS[course_design_step - 1]

    course, module = _get_course_and_module(course_id, module_id)
    if not course:
        return "Course not found"
    if not module:
        return "Module not found"

    module["status"] = f"In {queue_name_suffix.replace('_', ' ').title()}"
    course["modules"] = [module if m.get("_id") == module_id else m for m in course.get("modules", [])]

    atlas_client = AtlasClient()
    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={
        "$set": {
            "modules": course.get("modules", [])
        }
    })


    prev_step_resources = module.get(prev_step_directory, [])
    _handle_s3_file_transfer(course_id, module_id, prev_step_directory, step_directory, prev_step_resources)

    queue_payload = {
        "course_id": course_id,
        "module_id": module_id,
        "instructions": instructions
    }
    atlas_client.insert(step_directory, queue_payload)

    return course

async def save_changes_after_step(payload, course_design_step):
    course_id = payload['course_id']
    module_id = payload['module_id']
    reviewed_files = payload['reviewed_files']
    step_directory = COURSE_DESIGN_STEPS[course_design_step]

    course, module = _get_course_and_module(course_id, module_id)
    if not course:
        return "Course not found"
    if not module:
        return "Module not found"

    module[step_directory] = reviewed_files
    course["modules"] = [module if m.get("_id") == module_id else m for m in course.get("modules", [])]

    atlas_client = AtlasClient()
    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={
        "$set": {
            "modules": course.get("modules", [])
        }
    })

    return course
