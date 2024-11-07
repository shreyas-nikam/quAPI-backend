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

def get_courses():
    atlas_client = AtlasClient()
    courses = atlas_client.find("course_design")
    return courses
    
# generate_course_outline -> take in the input as the file and the instructions and generate the course outline
# TBD: Use Assistants api
def generate_course_outline(payload):
    input_file = payload['input_file']
    instructions = payload['instructions']
    llm = LLM("chatgpt")
    _get_prompt("COURSE_OUTLINE_PROMPT")
    inputs = {
        "INPUT_FILE": input_file,
        "INSTRUCTIONS": instructions
    }
    prompt = PromptTemplate(template=_get_prompt("COURSE_OUTLINE_PROMPT"), 
                            input_variables = ["INPUT_FILE", "INSTRUCTIONS"])

    response = _get_response(llm, prompt, inputs, output_type="string")

    return response

# clone_course -> takes in the course_id and clones the course
def clone_course(payload):
    course_id = payload['course_id']
    
    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})

    if not course:
        return "Course not found"
    
    course = course[0]
    course.pop("_id")

    new_course = course.copy()
    
    new_course_id = atlas_client.insert("course_design", new_course)
    
    return new_course_id

# delete_course -> takes in the course_id and deletes the course
def delete_course(payload):
    try:
        course_id = payload['course_id']
    except Exception as e:
        logging.error(f"No course id provided: {e}")
        return "Error in getting course_id"
    
    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})

    if not course:
        return "Course not found"
    
    course = course[0]
    
    atlas_client.delete("course_design", filter={"_id": ObjectId(course_id)})
    
    return "Course deleted"
    
def _get_file_type(file):
    if file.endswith(".md"):
        return "note"
    elif file.endswith(".png") or file.endswith(".jpg") or file.endswith(".jpeg"):
        return "image"
    else:
        return "file"


# create_course -> takes in the course name, course image, course description, files, course_outline, and creates a course object. also handles creation of modules
def create_course(payload):
    
    course_name = payload['course_name']
    course_image = payload['course_image']
    course_description = payload['course_description']
    files = payload['files']
    course_outline = payload['course_outline']
    course_status = "In Design"

    # upload the course image to s3 and get the link
    key = f"qu-course-design/{course_name}/course_image"
    s3_file_manager = S3FileManager()

    s3_file_manager.upload_file_obj(course_image, key)
    course_image_link = f"https://qucoursify.s3.amazonaws.com/{key}"

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


    course = {
        "course_name": course_name,
        "course_description": course_description,
        "course_image": course_image_link,
        "course_outline": course_outline,
        "status": course_status
    }

    course_id = atlas_client.insert("course_design", course)
    step_directory = COURSE_DESIGN_STEPS[0]

    modules = response.get("modules", []) 
    
    for module, index in enumerate(modules):
        module_id = ObjectId()
        modules[index]["module_id"] = module_id

        raw_resources = []

        for file in files:
            resource_type = _get_file_type(file)
            if(resource_type == "file"):
                key = f"qu-course-design/{course_id}/{str(module_id)}/{step_directory}/{file}"
                s3_file_manager.upload_file_obj(file, key)
                resource_link = f"https://qucoursify.s3.amazonaws.com/{key}"

            elif(resource_type == "note"):
                s3_file_manager = S3FileManager()

                key = f"qu-course-design/{course_id}/{str(module_id)}/{step_directory}/{file}"
                s3_file_manager.upload_file_obj(file, key)
                resource_link = f"https://qucoursify.s3.amazonaws.com/{key}"


            elif(resource_type == "image"):
                key = f"qu-course-design/{course_id}/{str(module_id)}/{step_directory}/{file}"
                s3_file_manager.upload_file_obj(file, key)
                resource_link = f"https://qucoursify.s3.amazonaws.com/{key}" 
                
            raw_resources += [{
                "resource_id": ObjectId(),
                "resource_type": resource_type,
                "resource_name": file,
                "resource_description": "",
                "resource_link": resource_link
            }]
        
        modules[index][step_directory] = raw_resources

    course["modules"] = modules

    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update=course)

    return course_id

# add_module -> takes in the course_id, module_name, module_description, and adds a module to the course
def add_module(payload):
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
    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update=course)

    return course

# get_course -> takes in the course_id and returns the course object
def get_course(payload):
    course_id = payload['course_id']

    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})

    if not course:
        return {}
    
    return course[0]

# add_resources_to_module -> takes in the course_id, module_id, resource_type, resource_name, resource_description, resource_file, and adds a resource to the module and to s3
def add_resources_to_module(payload, resource_id=""):
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

    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update=course)

    return course


# delete_resource_from_module -> takes in the course_id, module_id, resource_id, and deletes the resource from the module and from s3
def delete_resource_from_module(payload):
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

    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update=course)

    return course


def replace_resources_in_module(payload):
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

def submit_module_for_step(payload, course_design_step, queue_name_suffix):
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
    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update=course)

    prev_step_resources = module.get(prev_step_directory, [])
    _handle_s3_file_transfer(course_id, module_id, prev_step_directory, step_directory, prev_step_resources)

    queue_payload = {
        "course_id": course_id,
        "module_id": module_id,
        "instructions": instructions
    }
    atlas_client.insert(step_directory, queue_payload)

    return course

def save_changes_after_step(payload, course_design_step):
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
    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update=course)

    return course
