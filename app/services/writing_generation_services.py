from app.services.report_generation.generate_pdf import convert_markdown_to_pdf
from bson.objectid import ObjectId
from app.utils.s3_file_manager import S3FileManager
from urllib.parse import quote, unquote
from app.utils.atlas_client import AtlasClient
from openai import OpenAI
import os
import json
import logging
import datetime



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

def _convert_object_ids_to_strings(data):
    if isinstance(data, dict):
        return {key: _convert_object_ids_to_strings(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [_convert_object_ids_to_strings(item) for item in data]
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data
    
async def get_writings():
    atlas_client = AtlasClient()
    writings = atlas_client.find(collection_name="writing_design", filter={})
    writings = _convert_object_ids_to_strings(writings)
    return writings

async def delete_writing(writing_id):
    atlas_client = AtlasClient()
    writing = atlas_client.find(collection_name="writing_design", filter={"_id": ObjectId(writing_id)})
    if writing:
        atlas_client.delete(collection_name="writing_design", filter={"_id": ObjectId(writing_id)})
        return True
    return False

async def get_writing(writing_id):
    atlas_client = AtlasClient()
    writing = atlas_client.find(collection_name="writing_design", filter={"_id": ObjectId(writing_id)})
    if writing:
        writing = writing[0]
        writing = _convert_object_ids_to_strings(writing)
    return writing


identifier_mappings = {
    "research_report": "Research Report",
    "white_paper": "White Paper",
    "project_plan": "Project Plan",
    "e_book": "E-Book",
    "blog": "Blog",
    "news_letter": "Newsletter",
    "case_study": "Case Study",
    "key_insights": "Key Insights",
    "handout": "Handout",
}

async def writing_outline(files, instructions, identifier):
    prompt = identifier.upper() + "_PROMPT"
    identifier_text = identifier_mappings.get(identifier, "Writing")
    outline_instructions = _get_prompt(prompt)
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
            name=identifier_text + " Creator",
            instructions=outline_instructions,
            model=os.getenv("OPENAI_MODEL"),
            tools=[{"type": "file_search"}]
        )
        created_assistant_id = assistant.id  # Track the assistant

        vector_store = client.beta.vector_stores.create(
            name="writing Resources",
            expires_after={"days": 7, "anchor": "last_active_at"},
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
                "content": "Create the " + identifier_text + " in markdown format based on the instructions provided and the following user's instructions: " + instructions,
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
        # if the response starts with ```markdown, remove it
        if response.startswith("```"):
            response = response[3:].strip()
        if response.startswith("markdown"):
            response = response[8:].strip()
        # if the response ends with ``` remove it
        if response.endswith("```"):
            response = response[:-3].strip()
    except Exception as e:
        logging.error(f"Error in generating writing: {e}")
        return "# "+identifier_text+"\nHere's a sample: \n### 1: **On Machine Learning Applications in Investments**\n**Description**: This module provides an overview of the use of machine learning (ML) in investment practices, including its potential benefits and common challenges. It highlights examples where ML techniques have outperformed traditional investment models.\n\n**Learning Outcomes**:\n- Understand the motivations behind using ML in investment strategies.\n- Recognize the challenges and solutions in applying ML to finance.\n- Explore practical applications of ML for predicting equity returns and corporate performance.\n### 2: **Alternative Data and AI in Investment Research**\n**Description**: This module explores how alternative data sources combined with AI are transforming investment research by providing unique insights and augmenting traditional methods.\n\n**Learning Outcomes**:\n- Identify key sources of alternative data and their relevance in investment research.\n- Understand how AI can process and derive actionable insights from alternative data.\n- Analyze real-world use cases showcasing the impact of AI in research and decision-making.\n### 3: **Data Science for Active and Long-Term Fundamental Investing**\n**Description**: This module covers the integration of data science into long-term fundamental investing, discussing how quantitative analysis can enhance traditional methods.\n\n**Learning Outcomes**:\n- Learn the foundational role of data science in long-term investment strategies.\n- Understand the benefits of combining data science with active investing.\n- Evaluate case studies on the effective use of data science to support investment decisions.\n### 4: **Unlocking Insights and Opportunities**\n**Description**: This module focuses on techniques and strategies for using data-driven insights to identify market opportunities and enhance investment management processes.\n\n**Learning Outcomes**:\n- Grasp the importance of leveraging advanced data analytics for opportunity identification.\n- Understand how to apply insights derived from data to optimize investment outcomes.\n- Explore tools and methodologies that facilitate the unlocking of valuable investment insights.\n### 5: **Advances in Natural Language Understanding for Investment Management**\n**Description**: This module highlights the progression of natural language understanding (NLU) and its application in finance. It covers recent developments and their implications for asset management.\n\n**Learning Outcomes**:\n- Recognize advancements in NLU and their integration into investment strategies.\n- Explore trends and applications of NLU in financial data analysis.\n- Understand the technical challenges and solutions associated with implementing NLU tools.\n###"
    finally:
        # Clean up all created resources to avoid charges
        # store the assistant_id, vector_store_id, thread_id in mongodb
        atlas_client = AtlasClient()
        id = atlas_client.insert(
            collection_name="writing_design",
            data={
                "writing_outline": response
            }
            # data={
            #     "assistant_id": created_assistant_id,
            #     "vector_store_id": created_vector_store_id,
            #     "thread_id": created_thread_id
            # }
        )

        if created_assistant_id:
            client.beta.assistants.delete(created_assistant_id)
        if created_vector_store_id:
            client.beta.vector_stores.delete(created_vector_store_id)
        if created_thread_id:
            client.beta.threads.delete(created_thread_id)

    return {"writing_id": str(id), "writing": response}


async def create_writing(writing_id, writing_name, writing_description, writing_outline, files, writing_image, identifier):
    atlas_client = AtlasClient()
    s3_file_manager = S3FileManager()

    key = f"qu-course-design/{writing_id}/course_image/{writing_image.filename}"
    await s3_file_manager.upload_file_from_frontend(writing_image, key)
    key = quote(key)
    writing_image_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"
    writing = {
        "writing_name": writing_name,
        "writing_description": writing_description,
        "writing_outline": writing_outline,
        "writing_image": writing_image_link,
        "status": "In Design Phase",
        "identifier": identifier
    }
    atlas_client.update("writing_design", filter={"_id": ObjectId(writing_id)}, update={
        "$set": writing
    })

    raw_resources = []

    # store the files in s3
    for file in files:
        key = f"qu-writing-design/{writing_id}/raw_resources/{file.filename}"
        await s3_file_manager.upload_file_from_frontend(file, key)
        resource_id = ObjectId()
        key = quote(key)
        resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"
        resource = {
            "resource_id": resource_id,
            "resource_type": "File",
            "resource_name": file.filename,
            "resource_description": "File uploaded at the time of creation",
            "resource_link": resource_link
        }
        raw_resources.append(resource)

    atlas_client.update("writing_design", filter={"_id": ObjectId(writing_id)}, update={
        "$set": {"raw_resources": raw_resources}
    })
    writing = atlas_client.find(collection_name="writing_design", filter={"_id": ObjectId(writing_id)})[0]
    writing = _convert_object_ids_to_strings(writing)

    return writing


# TODO: Implement yet to be done
async def regenerate_outline(writing_id, instructions):
    client = OpenAI(api_key=os.getenv("OPENAI_KEY"))
    atlas_client = AtlasClient()
    writing = atlas_client.find(collection_name="writing_design", filter={"_id": ObjectId(writing_id)})
    if not writing:
        return "Writing not found"
    
    writing = writing[0]
    assistant_id, vector_store_id, thread_id = writing["assistant_id"], writing["vector_store_id"], writing["thread_id"]

    try:
        # Update the thread with the new user instructions
        updated_thread = client.beta.threads.update(
            thread_id=thread_id,
            messages=[{
                "role": "user",
                "content": "Regenerate the writing in markdown format based on the following user's updated instructions: " + instructions,
            }]
        )

        # Execute a new run with the updated thread
        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread_id, assistant_id=assistant_id
        )

        # Retrieve messages to fetch the updated content
        messages = list(client.beta.threads.messages.list(thread_id=thread_id, run_id=run.id))
        message_content = messages[0].content[0].text
        annotations = message_content.annotations
        citations = []

        # Process annotations for citations
        for index, annotation in enumerate(annotations):
            message_content.value = message_content.value.replace(annotation.text, f"[{index}]")
            if file_citation := getattr(annotation, "file_citation", None):
                cited_file = client.files.retrieve(file_citation.file_id)
                citations.append(f"[{index}] {cited_file.filename}")

        response = message_content.value
    except Exception as e:
        logging.error(f"Error in regenerating course outline: {e}")
        response = "An error occurred while regenerating the outline. Please try again or contact support."
    return response


async def convert_to_pdf(writing_id, markdown, template_name):

    file_id = ObjectId()
    convert_markdown_to_pdf(markdown=markdown, file_id=file_id, template_name=template_name)

    output_path = f"app/services/report_generation/outputs/{file_id}.pdf"

    key = f"qu-writing-design/{writing_id}/pre_processed_deliverables/{file_id}.pdf"
    # store the file in s3
    s3_file_manager = S3FileManager()
    await s3_file_manager.upload_file(output_path, key)

    key = quote(key)

    # store the filepath in mongodb
    atlas_client = AtlasClient()

    atlas_client.update(
        collection_name="writing_design",
        filter={"_id": ObjectId(writing_id)},
        update={
            "$set": {
                "pre_processed_deliverable": f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"
            }
        }
    )

    # remove file from os
    os.remove(output_path)

    # return file url in s3
    return f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

# will need to update the vector store with the new resource
async def add_resources_to_writing(writing_id, resource_type, resource_name, resource_description, resource_file):
    atlas_client = AtlasClient()
    writing = atlas_client.find(collection_name="writing_design", filter={"_id": ObjectId(writing_id)})
    if not writing:
        return False

    # store the file in s3
    s3_file_manager = S3FileManager()
    key = f"qu-writing-design/{writing_id}/resources/{resource_file.filename}"
    s3_file_manager.upload_file(resource_file.file, key)

    # store the resource in mongodb
    atlas_client.insert(
        collection_name="writing_resources",
        document={
            "writing_id": writing_id,
            "resource_type": resource_type,
            "resource_name": resource_name,
            "resource_description": resource_description,
            "resource_file": key
        }
    )

    return True


async def save_writing(writing_id, writing_outline):
    atlas_client = AtlasClient()
    
    history = atlas_client.find(collection_name="writing_design", filter={"_id": ObjectId(writing_id)})
    if not history:
        history={
                "writing_outline": writing_outline,
                "version": 1.0,
                "timestamp": datetime.datetime.now()
            }
    else:
        latest_version = history[-1]
        history={
                "writing_outline": writing_outline,
                "version": latest_version["version"] + 1.0,
                "timestamp": datetime.datetime.now()
            }
    atlas_client.update(
        collection_name="writing_design",
        filter={"_id": ObjectId(writing_id)},
        update={
            "$push": {
                "history": history
            }
        }
    )
       
    return True