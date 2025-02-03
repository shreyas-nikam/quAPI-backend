# generate_course_outline, clone_course, delete_course, create_course, add_module, add_resources_to_module, get_course, submit_module_for_content_generation, save_changes_post_content_generation, submit_module_for_structure_generation, save_changes_post_structure_generation, submit_module_for_deliverables_generation, save_changes_post_deliverables_generation, submit_for_publishing_pipeline
# the stages of the course design pipeline are: raw_resources, in_content_generation_queue, pre_processed_content, post_processed_content, in_structure_generation_queue, pre_processed_structure, post_processed_structure, in_deliverables_generation_queue, pre_processed_deliverables, post_processed_deliverables, in_publishing_queue, published
import requests
from fastapi.responses import StreamingResponse
from fastapi import FastAPI, HTTPException
from fastapi import HTTPException
from urllib.parse import urlparse
import mimetypes
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
from urllib.parse import quote, unquote


COURSE_DESIGN_STEPS = [
    "raw_resources",  # automatic
    "in_outline_generation_queue",  # expert-review-step
    "pre_processed_outline",  # expert-review-step
    "post_processed_outline",  # automatic
    "in_content_generation_queue",  # automatic
    "pre_processed_content",  # expert-review-step
    "post_processed_content",  # automatic
    "in_structure_generation_queue",  # automatic
    "pre_processed_structure",  # expert-review-step
    "post_processed_structure",  # automatic
    "in_deliverables_generation_queue",  # automatic
    "pre_processed_deliverables",  # expert-review-step
    "post_processed_deliverables",  # automatic
    "in_publishing_queue",  # automatic
    "published"  # expert-review-step
]


def _get_course_and_module(course_id, module_id):
    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})
    if not course:
        return "Course not found", None

    course = course[0]
    module = next((m for m in course.get("modules", []) if m.get(
        "module_id") == ObjectId(module_id)), None)
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
        return "Image"
    elif file.content_type.startswith("text"):
        return "Note"
    else:
        return "File"


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
    if files:
        for file in files:
            file_content = file.file.read()
            file.file.seek(0)

            print(file.filename)

            assistant_files_streams.append((file.filename, file_content))

        instructions = instructions + "Use the attached files to create the course outline."
        instructions = instructions + "### Files: " + ", ".join([file.filename for file in files])

    print("Instructions: ", instructions)
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
        if files:
            file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vector_store.id, files=assistant_files_streams
            )

            assistant = client.beta.assistants.update(
                assistant_id=assistant.id,
                tool_resources={"file_search": {"vector_store_ids": [vector_store.id]}},
            )

        else:
            assistant = client.beta.assistants.update(
                assistant_id=assistant.id,
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

        messages = list(client.beta.threads.messages.list(
            thread_id=thread.id, run_id=run.id))
        message_content = messages[0].content[0].text
        annotations = message_content.annotations
        citations = []

        for index, annotation in enumerate(annotations):
            message_content.value = message_content.value.replace(
                annotation.text, f"[{index}]")
            if file_citation := getattr(annotation, "file_citation", None):
                cited_file = client.files.retrieve(file_citation.file_id)
                citations.append(f"[{index}] {cited_file.filename}")

        response = message_content.value
    except Exception as e:
        logging.error(f"Error in generating course outline: {e}")
        return "# Module 1: **On Machine Learning Applications in Investments**\n**Description**: This module provides an overview of the use of machine learning (ML) in investment practices, including its potential benefits and common challenges. It highlights examples where ML techniques have outperformed traditional investment models.\n\n**Learning Outcomes**:\n- Understand the motivations behind using ML in investment strategies.\n- Recognize the challenges and solutions in applying ML to finance.\n- Explore practical applications of ML for predicting equity returns and corporate performance.\n### Module 2: **Alternative Data and AI in Investment Research**\n**Description**: This module explores how alternative data sources combined with AI are transforming investment research by providing unique insights and augmenting traditional methods.\n\n**Learning Outcomes**:\n- Identify key sources of alternative data and their relevance in investment research.\n- Understand how AI can process and derive actionable insights from alternative data.\n- Analyze real-world use cases showcasing the impact of AI in research and decision-making.\n### Module 3: **Data Science for Active and Long-Term Fundamental Investing**\n**Description**: This module covers the integration of data science into long-term fundamental investing, discussing how quantitative analysis can enhance traditional methods.\n\n**Learning Outcomes**:\n- Learn the foundational role of data science in long-term investment strategies.\n- Understand the benefits of combining data science with active investing.\n- Evaluate case studies on the effective use of data science to support investment decisions.\n### Module 4: **Unlocking Insights and Opportunities**\n**Description**: This module focuses on techniques and strategies for using data-driven insights to identify market opportunities and enhance investment management processes.\n\n**Learning Outcomes**:\n- Grasp the importance of leveraging advanced data analytics for opportunity identification.\n- Understand how to apply insights derived from data to optimize investment outcomes.\n- Explore tools and methodologies that facilitate the unlocking of valuable investment insights.\n### Module 5: **Advances in Natural Language Understanding for Investment Management**\n**Description**: This module highlights the progression of natural language understanding (NLU) and its application in finance. It covers recent developments and their implications for asset management.\n\n**Learning Outcomes**:\n- Recognize advancements in NLU and their integration into investment strategies.\n- Explore trends and applications of NLU in financial data analysis.\n- Understand the technical challenges and solutions associated with implementing NLU tools.\n###"
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

    atlas_client.insert("course_design", course)

    course = _convert_object_ids_to_strings(course)

    return course


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
async def create_course(course_name, course_description, course_outline, files, course_image, modulesAtCreation):
    course_status = "In Design Phase"

    s3_file_manager = S3FileManager()
    atlas_client = AtlasClient()
    modules = []
    if modulesAtCreation:
        # convert the course outline to modules
        course_outline_to_modules_prompt = _get_prompt("COURSE_OUTLINE_TO_MODULES_PROMPT")
        inputs = {"COURSE_OUTLINE": course_outline}
        prompt = PromptTemplate(template=course_outline_to_modules_prompt,
                                input_variables=["COURSE_OUTLINE"])

        llm = LLM("chatgpt")
        response = _get_response(llm, prompt, inputs, output_type="json")
        modules = response.get("modules", [])

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

    raw_resources = []
    if files:
        for file in files:
            resource_type = _get_file_type(file)
            file_id = str(ObjectId())

            key = f"qu-course-design/{course_id}/{step_directory}/{file_id}.{file.filename.split('.')[-1]}"
            await s3_file_manager.upload_file_from_frontend(file, key)
            key = quote(key)
            resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

            raw_resources += [{
                "resource_id": ObjectId(),
                "resource_type": resource_type,
                "resource_name": file.filename,
                "resource_description": "File uploaded at course creation",
                "resource_link": resource_link
            }]

    course[step_directory] = raw_resources

    if modulesAtCreation:
        for index, module in enumerate(modules):
            module_id = ObjectId()
            modules[index]["module_id"] = module_id
            modules[index]["status"] = "In Design Phase"

            raw_resources = []

            if files:
                for file in files:
                    resource_type = _get_file_type(file)
                    file_id = str(ObjectId())
                    file.file.seek(0)
                    key = f"qu-course-design/{course_id}/{step_directory}/{file_id}.{file.filename.split('.')[-1]}"
                    await s3_file_manager.upload_file_from_frontend(file, key)
                    key = quote(key)
                    resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

                    raw_resources += [{
                        "resource_id": ObjectId(),
                        "resource_type": resource_type,
                        "resource_name": file.filename,
                        "resource_description": "File uploaded at course creation",
                        "resource_link": resource_link
                    }]

                modules[index][step_directory] = raw_resources

    course["modules"] = modules

    atlas_client.insert("course_design", course)

    course = _convert_object_ids_to_strings(course)
    return course


def _get_resource_key_from_link(resource_link):
    resource_prefix = resource_link.split("aws.com/")[1]
    # unquote the key
    resource_key = unquote(resource_prefix)
    return resource_key


# add_module -> takes in the course_id, module_name, module_description, and adds a module to the course
async def add_module(course_id, module_name, module_description):
    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})

    if not course:
        return "Course not found"

    course = course[0]
    raw_resources = course.get("raw_resources", [])

    module_id = ObjectId()

    raw_resources_added_to_module = []
    # add the raw_resources to the module
    for resource in raw_resources:
        resource_type = resource.get("resource_type")
        resource_name = resource.get("resource_name")
        resource_description = resource.get("resource_description")
        resource_link = resource.get("resource_link")
        resource_id = ObjectId()

        resource_key = _get_resource_key_from_link(resource_link)
        key = f"qu-course-design/{course_id}/{str(module_id)}/raw_resources/{resource_name}"
        s3_file_manager = S3FileManager()
        s3_file_manager.copy_file(resource_key, key)
        key = quote(key)
        resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

        raw_resources_added_to_module.append({"resource_id": resource_id,
                                              "resource_type": resource_type,
                                              "resource_name": resource_name,
                                              "resource_description": resource_description,
                                              "resource_link": resource_link
                                              })

    modules = course.get("modules", [])
    module = {"module_id": module_id,
              "module_name": module_name,
              "module_description": module_description,
              "status": "In Design Phase",
              "raw_resources": raw_resources_added_to_module
              }

    modules.append(module)
    course["modules"] = modules

    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={"$set": {"modules": modules
                                                                                               }
                                                                                      })

    course = _convert_object_ids_to_strings(course)
    return course

# get_course -> takes in the course_id and returns the course object


async def get_course(course_id):

    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})

    if not course:
        return {}

    course = course[0]

    # populate the additional artifacts
    artifacts = []
    for artifact in course.get("additional_artifacts", []):
        artifact_type = artifact.get("artifact_type")
        artifact_id = artifact.get("artifact_id")

        if artifact_type == "Lecture":
            writing = atlas_client.find("lecture_design", filter={"_id": ObjectId(artifact_id)})
            if writing:
                artifacts.append(writing[0])
        elif artifact_type == "Lab":
            lab = atlas_client.find("lab_design", filter={"_id": ObjectId(artifact_id)})
            if lab:
                artifacts.append(lab[0])
        else:

            lecture = atlas_client.find("writing_design", filter={"_id": ObjectId(artifact_id)})
            if lecture:
                artifacts.append(lecture[0])

    course['additional_artifacts'] = artifacts

    course = _convert_object_ids_to_strings(course)

    return course

# add_resources_to_module -> takes in the course_id, module_id, resource_type, resource_name, resource_description, resource_file, and adds a resource to the module and to s3


async def add_resources_to_module(course_id, module_id, resource_type, resource_name, resource_description, resource_file, resource_id=None, course_design_step=0):
    s3_file_manager = S3FileManager()
    step_directory = COURSE_DESIGN_STEPS[course_design_step]
    resource_id = ObjectId() if not resource_id else ObjectId(resource_id)

    if resource_type in {"File", "Assessment", "Image", "Slide_Generated", "Slide_Content", "Video"}:
        # resource file is the file
        key = f"qu-course-design/{course_id}/{module_id}/{step_directory}/{str(resource_id)}."+resource_file.filename.split(".")[-1]
        await s3_file_manager.upload_file_from_frontend(resource_file, key)
        key = quote(key)
        resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

    elif resource_type == "Image":
        # resource file is the image
        key = f"qu-course-design/{course_id}/{module_id}/{step_directory}/{str(resource_id)}."+resource_file.filename.split(".")[-1]
        await s3_file_manager.upload_file_from_frontend(resource_file, key)
        key = quote(key)
        resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

    elif resource_type == "Link":
        # resource file is the resource link
        resource_description, resource_link = resource_description.split(
            "###LINK###")

    elif resource_type == "Note":
        # resource file is the description of the note
        resource_description, resource_note = resource_description.split(
            "###NOTE###")
        note_id = ObjectId()
        resource_file_name = str(note_id) + ".md"
        with open(resource_file_name, "w") as file:
            file.write(resource_note)

        key = f"qu-course-design/{course_id}/{module_id}/{step_directory}/{resource_file_name}"
        await s3_file_manager.upload_file(resource_file_name, key)
        key = quote(key)

        # remove the temp file
        os.remove(resource_file_name)
        resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})
    if not course:
        return "Course not found"

    course = course[0]
    modules = course.get("modules", [])

    for index, module in enumerate(modules):
        if module.get("module_id") == ObjectId(module_id):
            resources = module.get(f"{step_directory}", [])
            resource = {
                "resource_id": resource_id,
                "resource_type": resource_type,
                "resource_name": resource_name,
                "resource_description": resource_description,
                "resource_link": resource_link
            }
            resources.append(resource)
            modules[index][step_directory] = resources
            break

    course["modules"] = modules

    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={
        "$set": {
            "modules": modules
        }
    }
    )

    course = _convert_object_ids_to_strings(course)

    return course


# delete_resource_from_module -> takes in the course_id, module_id, resource_id, and deletes the resource from the module and from s3
async def delete_resources_from_module(course_id, module_id, resource_id, course_design_step=0):
    step_directory = COURSE_DESIGN_STEPS[course_design_step]

    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={
                               "_id": ObjectId(course_id)})

    if not course:
        return "Course not found"

    course = course[0]
    modules = course.get("modules", [])
    for module in modules:
        if module.get("module_id") == ObjectId(module_id):
            resources = module.get(step_directory, [])
            for resource in resources:
                if resource.get("resource_id") == ObjectId(resource_id):
                    resources.remove(resource)
                    break
            module[step_directory] = resources
            break

    course["modules"] = modules

    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={"$set": {"modules": modules}})

    course = _convert_object_ids_to_strings(course)

    return course

# replace the resource in the module and s3


async def replace_resources_in_module(course_id, module_id, resource_id, resource_name, resource_type, resource_description, resource_file, course_design_step=0):

    # delete the resource with the resource id, and add the new resource with the same id
    course = await delete_resources_from_module(course_id=course_id,
                                                module_id=module_id,
                                                resource_id=resource_id,
                                                course_design_step=course_design_step)

    # add the new resource
    course = await add_resources_to_module(course_id=course_id,
                                           module_id=module_id,
                                           resource_type=resource_type,
                                           resource_name=resource_name,
                                           resource_description=resource_description,
                                           resource_file=resource_file,
                                           resource_id=resource_id,
                                           course_design_step=course_design_step)

    course = _convert_object_ids_to_strings(course)

    return course


def _handle_s3_file_transfer(course_id, module_id, prev_step_directory, step_directory, resources):
    s3_file_manager = S3FileManager()
    for resource in resources:
        next_step_key = f"qu-course-design/{course_id}/{module_id}/{step_directory}/{resource['resource_link'].split('/')[-1]}"
        prev_step_key = f"qu-course-design/{course_id}/{module_id}/{prev_step_directory}/{resource['resource_link'].split('/')[-1]}"
        s3_file_manager.copy_file(prev_step_key, next_step_key)


def _rollback_s3_file_transfer(course_id, module_id, step_directory, resources):
    s3_file_manager = S3FileManager()
    for resource in resources:
        delete_file_key = f"qu-course-design/{course_id}/{module_id}/{step_directory}/{resource["resource_link"].split('/')[-1]}"
        s3_file_manager.delete_file(delete_file_key)


async def remove_module_from_step(course_id, module_id, course_design_step, queue_name_suffix, instructions=""):
    print("In remove_module_from_step")
    step_directory = COURSE_DESIGN_STEPS[course_design_step]
    prev_step_directory = COURSE_DESIGN_STEPS[course_design_step - 1]

    course, module = _get_course_and_module(course_id, module_id)

    if not course:
        return "Course not found"
    if not module:
        return "Module not found"

    # module["status"] = f"{queue_name_suffix.replace('_', ' ').title()}"
    # if instructions:
    #     module["instructions"] = instructions
    course["modules"] = [module if m.get(
        "module_id") == module_id else m for m in course.get("modules", [])]

    atlas_client = AtlasClient()
    # atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={"$set": {"modules": course.get("modules", [])}
    # })

    step_directory_resources = module.get(step_directory, [])
    _rollback_s3_file_transfer(
        course_id, module_id, step_directory, step_directory_resources)
    # _handle_s3_file_transfer(
    #     course_id, module_id, prev_step_directory, step_directory, prev_step_resources)

    queue_payload = {"course_id": course_id,
                     "module_id": module_id,
                     }

    if instructions:
        queue_payload["instructions"] = instructions

    # Check if the document already exists
    existing_item = atlas_client.find(
        step_directory, {"course_id": course_id, "module_id": module_id}, limit=1)

    if existing_item:
        # If it exists, update it
        atlas_client.delete(
            step_directory, {"course_id": course_id, "module_id": module_id})

    course = _convert_object_ids_to_strings(course)

    return True


async def submit_module_for_step(course_id, module_id, course_design_step, queue_name_suffix, instructions=""):
    step_directory = COURSE_DESIGN_STEPS[course_design_step]
    prev_step_directory = COURSE_DESIGN_STEPS[course_design_step - 1]

    course, module = _get_course_and_module(course_id, module_id)

    if not course:
        return "Course not found"
    if not module:
        return "Module not found"

    if course_design_step == 1:
        await remove_module_from_step(course_id, module_id, 12, "in_publishing_queue", instructions)
        await remove_module_from_step(course_id, module_id, 10, "in_deliverables_generation_queue", instructions)
        await remove_module_from_step(course_id, module_id, 7, "in_structure_generation_queue", instructions)
        await remove_module_from_step(course_id, module_id, 4, "in_content_generation_queue", instructions)

    if course_design_step == 4:
        await remove_module_from_step(course_id, module_id, 12, "in_publishing_queue", instructions)
        await remove_module_from_step(course_id, module_id, 10, "in_deliverables_generation_queue", instructions)
        await remove_module_from_step(course_id, module_id, 7, "in_structure_generation_queue", instructions)

    if course_design_step == 7:
        await remove_module_from_step(course_id, module_id, 12, "in_publishing_queue", instructions)
        await remove_module_from_step(course_id, module_id, 10, "in_deliverables_generation_queue", instructions)

    if course_design_step == 10:
        await remove_module_from_step(course_id, module_id, 12, "in_publishing_queue", instructions)

    module["status"] = f"{queue_name_suffix.replace('_', ' ').title()}"
    if instructions:
        module["instructions"] = instructions
    course["modules"] = [module if m.get(
        "module_id") == module_id else m for m in course.get("modules", [])]

    atlas_client = AtlasClient()
    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={"$set": {"modules": course.get("modules", [])}
                                                                                      })

    prev_step_resources = module.get(prev_step_directory, [])
    _handle_s3_file_transfer(
        course_id, module_id, prev_step_directory, step_directory, prev_step_resources)

    queue_payload = {
        "course_id": course_id,
        "module_id": module_id,
    }

    if instructions:
        queue_payload["instructions"] = instructions

    # Check if the document already exists
    existing_item = atlas_client.find(
        step_directory, {"course_id": course_id, "module_id": module_id}, limit=1)

    if existing_item:
        # If it exists, update it
        atlas_client.update(step_directory, {"course_id": course_id, "module_id": module_id}, {"$set": queue_payload})
    else:
        # If it does not exist, insert a new document
        atlas_client.insert(step_directory, queue_payload)

    course = _convert_object_ids_to_strings(course)

    return course


async def submit_module_for_unpublish(course_id, module_id, course_design_step, queue_name_suffix, instructions=""):
    step_directory = COURSE_DESIGN_STEPS[course_design_step]
    prev_step_directory = COURSE_DESIGN_STEPS[course_design_step - 1]

    course, module = _get_course_and_module(course_id, module_id)

    if not course:
        return "Course not found"
    if not module:
        return "Module not found"

    module["status"] = prev_step_directory
    if instructions:
        module["instructions"] = instructions
    course["modules"] = [module if m.get(
        "module_id") == module_id else m for m in course.get("modules", [])]

    atlas_client = AtlasClient()
    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={"$set": {"modules": course.get("modules", [])}
                                                                                      })

    prev_step_resources = module.get(prev_step_directory, [])
    _handle_s3_file_transfer(
        course_id, module_id, prev_step_directory, step_directory, prev_step_resources)

    queue_payload = {        
        "course_id": course_id,
        "module_id": module_id,
    }

    if instructions:
        queue_payload["instructions"] = instructions

    # Check if the document already exists
    existing_item = atlas_client.find(step_directory, {"course_id": course_id, "module_id": module_id}, limit=1)

    if existing_item:
        # If it exists, update it
        atlas_client.update(step_directory, {"course_id": course_id, "module_id": module_id}, {"$set": queue_payload})
    else:
        # If it does not exist, insert a new document
        atlas_client.insert(step_directory, queue_payload)

    course = _convert_object_ids_to_strings(course)

    return course


async def submit_course_for_publishing(course_id: str, step_directory: str, queue_name_suffix: str):
    # Initialize Atlas Client
    atlas_client = AtlasClient()

    # Validate step_directory
    step_directory = COURSE_DESIGN_STEPS[step_directory]
    if not step_directory:
        return "Invalid step directory", None

    # Fetch course by ID
    course = atlas_client.find("course_design", filter={"_id": ObjectId(course_id)})
    if not course:
        return "Course not found", None
    course = course[0]

    # Format status using queue_name_suffix and update the course
    formatted_status = queue_name_suffix.replace('_', ' ').title()
    update_status_payload = {"$set": {"status": formatted_status}}

    update_response = atlas_client.update(
        "course_design", 
        filter={"_id": ObjectId(course_id)}, 
        update=update_status_payload
    )

    if not update_response:
        raise ValueError("Failed to update course status.")

    # Create the queue payload
    queue_payload = {"course_id": course_id}

    # Check if the document exists in the step directory
    existing_item = atlas_client.find(step_directory, {"course_id": course_id}, limit=1)
    if existing_item:
        # Update the existing document
        update_response = atlas_client.update(step_directory, {"course_id": course_id}, {"$set": queue_payload})
        if not update_response:
            raise ValueError("Failed to update the queue document.")
    else:
        # Insert a new document if it doesn't exist
        insert_response = atlas_client.insert(step_directory, queue_payload)
        if not insert_response:
            raise ValueError("Failed to insert new queue document.")

    # Convert object IDs to strings before returning
    course = _convert_object_ids_to_strings(course)

    return course, None  # Return course data with no errors


async def submit_module_for_deliverables_step(course_id, module_id, course_design_step, voice_name, assessment, chatbot, queue_name_suffix):
    step_directory = COURSE_DESIGN_STEPS[course_design_step]
    prev_step_directory = COURSE_DESIGN_STEPS[course_design_step - 1]

    course, module = _get_course_and_module(course_id, module_id)

    if not course:
        return "Course not found"
    if not module:
        return "Module not found"

    module["status"] = f"{queue_name_suffix.replace('_', ' ').title()}"
    module["assessment"] = assessment
   
    course["modules"] = [module if m.get("module_id") == module_id else m for m in course.get("modules", [])]

    atlas_client = AtlasClient()
    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={"$set": {"modules": course.get("modules", [])
                                                                                               }
                                                                                      })

    prev_step_resources = module.get(prev_step_directory, [])
    _handle_s3_file_transfer(
        course_id, module_id, prev_step_directory, step_directory, prev_step_resources)

    queue_payload = {"course_id": course_id,
                     "module_id": module_id,
                     }

    if voice_name:
        queue_payload["voice_name"] = voice_name
        queue_payload["chatbot"] = chatbot

    # Check if the document already exists
    existing_item = atlas_client.find(step_directory, {"course_id": course_id, "module_id": module_id}, limit=1)

    if existing_item:
        # If it exists, update it
        atlas_client.update(step_directory, {"course_id": course_id, "module_id": module_id}, {"$set": queue_payload})
    else:
        # If it does not exist, insert a new document
        atlas_client.insert(step_directory, queue_payload)

    course = _convert_object_ids_to_strings(course)

    return course


async def fetch_pdf(url):
    try:
        # Fetch the PDF from the provided URL
        response = requests.get(url, stream=True)
        response.raise_for_status()

        # Return the PDF as a StreamingResponse
        return StreamingResponse(response.raw, media_type="application/pdf")
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to fetch PDF: {str(e)}")


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
        content_type = response.get("ContentType") or mimetypes.guess_type(key)[
            0] or "application/octet-stream"

        return {            
            "content": file_content.decode("utf-8"),
            "content_type": content_type,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def fetch_quizdata(url):
    try:
        # Fetch quiz data from the URL (e.g., using requests or an async method)
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception if the request fails
        quiz_data = response.json()  # Parse the response as JSON
        return quiz_data
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Error fetching quiz data: {e}")


async def add_artifact_to_course(course_id, artifact_type, artifact_id):
    atlas_client = AtlasClient()
    course = atlas_client.find("course_design", filter={               "_id": ObjectId(course_id)})
    if not course:
        return "Course not found"
    course = course[0]
    additional_artifacts = course.get("additional_artifacts", [])

    additional_artifacts.append({        "artifact_type": artifact_type,
        "artifact_id": artifact_id
    })

    atlas_client.update("course_design", filter={"_id": ObjectId(course_id)}, update={        "$set": {            "additional_artifacts": additional_artifacts
        }
    })
    course = await get_course(course_id)
    course = _convert_object_ids_to_strings(course)
    return course


async def fetch_qu_skill_bridge_course_id(course_id):
    atlas_client = AtlasClient()
    course = atlas_client.find("courses", filter={"course_id": ObjectId(course_id)})
    if not course:
        return "Course not found"
    course = course[0]
    return str(course["_id"])
