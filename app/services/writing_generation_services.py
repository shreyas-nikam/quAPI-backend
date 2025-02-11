from app.utils.llm import LLM
from langchain_core.prompts.prompt import PromptTemplate
from app.services.report_generation.generate_pdf import convert_markdown_to_pdf
from bson.objectid import ObjectId
from app.utils.s3_file_manager import S3FileManager
from urllib.parse import quote
from app.utils.atlas_client import AtlasClient
from openai import OpenAI
import os
import json
import logging
import datetime
import ast

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

async def generate_templates(files, identifier):
    prompt = "GENERATE_TEMPLATES_FOR_WRITING_PROMPT"
    
    identifier_text = identifier_mappings.get(identifier, "Writing")
    templates_instructions = _get_prompt(prompt)
    client = OpenAI(api_key=os.getenv("OPENAI_KEY"))

    assistant_files_streams = []
    if files:
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
            instructions=templates_instructions,
            model=os.getenv("OPENAI_MODEL"),
            tools=[{"type": "file_search"}]
        )

        created_assistant_id = assistant.id  # Track the assistant

        vector_store = client.beta.vector_stores.create(
            name="writing Resources",
            expires_after={"days": 7, "anchor": "last_active_at"},
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
                "content": "Generate templates for " + identifier_text + " based on the instructions provided.",
            }]
        )

        created_thread_id = thread.id  # Track the thread

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id, assistant_id=assistant.id, poll_interval_ms=5000
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
        try:
            response = ast.literal_eval(response)
        except:
            response = ast.literal_eval(response[response.index("["):response.rindex("]") + 1])

        return {
            "templates": response
        }

    except Exception as e:
        return {
            "templates": [
                {
                    "template_name": "Student Template",
                    "template_content": f"### {identifier_text} \nInstructions\n\n- Create a {identifier_text} for students. \n*Objectives*: \n  - Simplify complex concepts. \n  - Include interactive elements. \n  - Provide practical examples. \n*Target Audience*: Students and beginners"
                },
                {
                    "template_name": "Professional Template",
                    "template_content": f"### {identifier_text} \nInstructions\n\n- Develop a {identifier_text} for professionals. \n*Objectives*: \n  - Provide in-depth analysis. \n  - Include advanced concepts. \n  - Offer actionable insights. \n*Target Audience*: Industry experts and practitioners"
                },
                {
                    "template_name": "Industry Experts Template",
                    "template_content": f"### {identifier_text} \nInstructions\n\n- Create a {identifier_text} for industry experts. \n*Objectives*: \n  - Explore cutting-edge topics. \n  - Include advanced case studies. \n  - Offer expert-level insights. \n*Target Audience*: Industry leaders and experts"
                },
                {
                    "template_name": "General Audience Template",
                    "template_content": f"### {identifier_text} \nInstructions\n\n- Develop a {identifier_text} for a general audience. \n*Objectives*: \n  - Simplify complex topics. \n  - Include relatable examples. \n  - Offer practical advice. \n*Target Audience*: General readers and enthusiasts"
                }
            ]
        }
    
    finally:
        # Clean up all created resources to avoid charges
        if created_assistant_id:
            client.beta.assistants.delete(created_assistant_id)
        if created_vector_store_id:
            client.beta.vector_stores.delete(created_vector_store_id)
        if created_thread_id:
            client.beta.threads.delete(created_thread_id)

async def writing_outline(files, instructions, identifier):
    prompt = identifier.upper() + "_PROMPT"
    identifier_text = identifier_mappings.get(identifier, "Writing")
    outline_instructions = _get_prompt(prompt)
    client = OpenAI(api_key=os.getenv("OPENAI_KEY"))

    assistant_files_streams = []
    if files:
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
                "content": "Create the " + identifier_text + " in markdown format based on the instructions provided and the following user's instructions: " + instructions,
            }]
        )
        created_thread_id = thread.id  # Track the thread

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id, assistant_id=assistant.id, poll_interval_ms=5000
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
        if response.startswith("```"):
            response = response[3:].strip()
        if response.startswith("markdown"):
            response = response[8:].strip()
        if response.endswith("```"):
            response = response[:-3].strip()
    except Exception as e:
        logging.error(f"Error in generating writing: {e}")
        response = "# "+identifier_text+"\nHere's a sample: \n### 1: **On Machine Learning Applications in Investments**\n**Description**: This module provides an overview of the use of machine learning (ML) in investment practices, including its potential benefits and common challenges. It highlights examples where ML techniques have outperformed traditional investment models.\n\n**Learning Outcomes**:\n- Understand the motivations behind using ML in investment strategies.\n- Recognize the challenges and solutions in applying ML to finance.\n- Explore practical applications of ML for predicting equity returns and corporate performance.\n### 2: **Alternative Data and AI in Investment Research**\n**Description**: This module explores how alternative data sources combined with AI are transforming investment research by providing unique insights and augmenting traditional methods.\n\n**Learning Outcomes**:\n- Identify key sources of alternative data and their relevance in investment research.\n- Understand how AI can process and derive actionable insights from alternative data.\n- Analyze real-world use cases showcasing the impact of AI in research and decision-making.\n### 3: **Data Science for Active and Long-Term Fundamental Investing**\n**Description**: This module covers the integration of data science into long-term fundamental investing, discussing how quantitative analysis can enhance traditional methods.\n\n**Learning Outcomes**:\n- Learn the foundational role of data science in long-term investment strategies.\n- Understand the benefits of combining data science with active investing.\n- Evaluate case studies on the effective use of data science to support investment decisions.\n### 4: **Unlocking Insights and Opportunities**\n**Description**: This module focuses on techniques and strategies for using data-driven insights to identify market opportunities and enhance investment management processes.\n\n**Learning Outcomes**:\n- Grasp the importance of leveraging advanced data analytics for opportunity identification.\n- Understand how to apply insights derived from data to optimize investment outcomes.\n- Explore tools and methodologies that facilitate the unlocking of valuable investment insights.\n### 5: **Advances in Natural Language Understanding for Investment Management**\n**Description**: This module highlights the progression of natural language understanding (NLU) and its application in finance. It covers recent developments and their implications for asset management.\n\n**Learning Outcomes**:\n- Recognize advancements in NLU and their integration into investment strategies.\n- Explore trends and applications of NLU in financial data analysis.\n- Understand the technical challenges and solutions associated with implementing NLU tools.\n###"
        # return {"writing_id": str(ObjectId()), "writing":"# "+identifier_text+"\nHere's a sample: \n### 1: **On Machine Learning Applications in Investments**\n**Description**: This module provides an overview of the use of machine learning (ML) in investment practices, including its potential benefits and common challenges. It highlights examples where ML techniques have outperformed traditional investment models.\n\n**Learning Outcomes**:\n- Understand the motivations behind using ML in investment strategies.\n- Recognize the challenges and solutions in applying ML to finance.\n- Explore practical applications of ML for predicting equity returns and corporate performance.\n### 2: **Alternative Data and AI in Investment Research**\n**Description**: This module explores how alternative data sources combined with AI are transforming investment research by providing unique insights and augmenting traditional methods.\n\n**Learning Outcomes**:\n- Identify key sources of alternative data and their relevance in investment research.\n- Understand how AI can process and derive actionable insights from alternative data.\n- Analyze real-world use cases showcasing the impact of AI in research and decision-making.\n### 3: **Data Science for Active and Long-Term Fundamental Investing**\n**Description**: This module covers the integration of data science into long-term fundamental investing, discussing how quantitative analysis can enhance traditional methods.\n\n**Learning Outcomes**:\n- Learn the foundational role of data science in long-term investment strategies.\n- Understand the benefits of combining data science with active investing.\n- Evaluate case studies on the effective use of data science to support investment decisions.\n### 4: **Unlocking Insights and Opportunities**\n**Description**: This module focuses on techniques and strategies for using data-driven insights to identify market opportunities and enhance investment management processes.\n\n**Learning Outcomes**:\n- Grasp the importance of leveraging advanced data analytics for opportunity identification.\n- Understand how to apply insights derived from data to optimize investment outcomes.\n- Explore tools and methodologies that facilitate the unlocking of valuable investment insights.\n### 5: **Advances in Natural Language Understanding for Investment Management**\n**Description**: This module highlights the progression of natural language understanding (NLU) and its application in finance. It covers recent developments and their implications for asset management.\n\n**Learning Outcomes**:\n- Recognize advancements in NLU and their integration into investment strategies.\n- Explore trends and applications of NLU in financial data analysis.\n- Understand the technical challenges and solutions associated with implementing NLU tools.\n###"}
    finally:
        
        # Clean up all created resources to avoid charges
        # store the assistant_id, vector_store_id, thread_id in mongodb
        atlas_client = AtlasClient()
        id = atlas_client.insert(
            collection_name="writing_design",
            data={
                "writing_outline": response,
                "initial_instructions": instructions
            }
            # data={
            #       "writing_outline": response,
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
    writing = atlas_client.find(collection_name="writing_design", filter={"_id": ObjectId(writing_id)})[0]
    instructions = writing.get("initial_instructions", "")

    raw_resources = []
    history = []
    if files:
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

    history.append({
        "writing_outline": writing_outline,
        "version": 1.0,
        "timestamp": datetime.datetime.now(),
        "resources": raw_resources,
        "feedback": instructions
    })
    atlas_client.update("writing_design", filter={"_id": ObjectId(writing_id)}, update={
        "$set": {"history": history}
    })
    atlas_client.update("writing_design", filter={"_id": ObjectId(writing_id)}, update={
        "$set": {"all_resources": raw_resources}
    })
    writing = atlas_client.find(collection_name="writing_design", filter={"_id": ObjectId(writing_id)})[0]
    writing = _convert_object_ids_to_strings(writing)

    return writing

async def regenerate_outline(writing_id, instructions, previous_outline, selected_resources, identifier):
    selected_resources = json.loads(selected_resources)
    print(selected_resources)
    client = OpenAI(api_key=os.getenv("OPENAI_KEY"))
    atlas_client = AtlasClient()
    writing = atlas_client.find(collection_name="writing_design", filter={"_id": ObjectId(writing_id)})
    if not writing:
        return "Writing not found"
    
    writing = writing[0]

    prompt = _get_prompt("REGENERATE_DRAFT_PROMPT")

    prompt = prompt.replace("{DRAFT}", previous_outline)
    prompt = prompt.replace("{USER_INSTRUCTIONS}", instructions)

    files = []
    for resource in selected_resources:
        file = resource.get("resource_link")
        files.append(file)



    # Track created resources
    created_assistant_id = None

    identifier_text = identifier_mappings.get(identifier, "Writing")

    try:
        assistant = client.beta.assistants.create(
            name=identifier_text + " Creator",
            instructions=prompt,
            model=os.getenv("OPENAI_MODEL"),
            tools=[{"type": "file_search"}]
        )
        created_assistant_id = assistant.id  # Track the assistant

        vector_store = client.beta.vector_stores.create(
            name="writing Resources",
            expires_after={"days": 7, "anchor": "last_active_at"},
        )
        created_vector_store_id = vector_store.id  # Track the vector store
        if files:
            file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vector_store.id, files=files
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
                "content": "Create the " + identifier_text + " in markdown format based on the instructions provided and the following user's instructions: " + instructions,
            }]
        )
        created_thread_id = thread.id  # Track the thread

        run = client.beta.threads.runs.create_and_poll(
            thread_id=thread.id, assistant_id=assistant.id, poll_interval_ms=5000
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

        if response.startswith("```"):
            response = response[3:].strip()
        if response.startswith("markdown"):
            response = response[8:].strip()
        if response.endswith("```"):
            response = response[:-3].strip()

        history = writing.get("history", [])
        latest_version = history[-1]
        history.append({
            "writing_outline": response,
            "version": latest_version["version"] + 1.0,
            "timestamp": datetime.datetime.now(),
            "resources": selected_resources,
            "feedback": instructions
        })

        atlas_client.update(
            collection_name="writing_design",
            filter={"_id": ObjectId(writing_id)},
            update={
                "$set": {
                    "history": history
                }
            }
        )

    except Exception as e:
        return {"writing_id": str(id), "writing": "Something went wrong. Please try again later. But here's a sample response:\n\n# "+identifier_text+"\nHere's a sample: \n### 1: **On Machine Learning Applications in Investments**\n**Description**: This module provides an overview of the use of machine learning (ML) in investment practices, including its potential benefits and common challenges. It highlights examples where ML techniques have outperformed traditional investment models.\n\n**Learning Outcomes**:\n- Understand the motivations behind using ML in investment strategies.\n- Recognize the challenges and solutions in applying ML to finance.\n- Explore practical applications of ML for predicting equity returns and corporate performance.\n### 2: **Alternative Data and AI in Investment Research**\n**Description**: This module explores how alternative data sources combined with AI are transforming investment research by providing unique insights and augmenting traditional methods.\n\n**Learning Outcomes**:\n- Identify key sources of alternative data and their relevance in investment research.\n- Understand how AI can process and derive actionable insights from alternative data.\n- Analyze real-world use cases showcasing the impact of AI in research and decision-making.\n### 3: **Data Science for Active and Long-Term Fundamental Investing**\n**Description**: This module covers the integration of data science into long-term fundamental investing, discussing how quantitative analysis can enhance traditional methods.\n\n**Learning Outcomes**:\n- Learn the foundational role of data science in long-term investment strategies.\n- Understand the benefits of combining data science with active investing.\n- Evaluate case studies on the effective use of data science to support investment decisions.\n### 4: **Unlocking Insights and Opportunities**\n**Description**: This module focuses on techniques and strategies for using data-driven insights to identify market opportunities and enhance investment management processes.\n\n**Learning Outcomes**:\n- Grasp the importance of leveraging advanced data analytics for opportunity identification.\n- Understand how to apply insights derived from data to optimize investment outcomes.\n- Explore tools and methodologies that facilitate the unlocking of valuable investment insights.\n### 5: **Advances in Natural Language Understanding for Investment Management**\n**Description**: This module highlights the progression of natural language understanding (NLU) and its application in finance. It covers recent developments and their implications for asset management.\n\n**Learning Outcomes**:\n- Recognize advancements in NLU and their integration into investment strategies.\n- Explore trends and applications of NLU in financial data analysis.\n- Understand the technical challenges and solutions associated with implementing NLU tools.\n###"}
    
    finally:
        # Clean up all created resources to avoid charges
        if created_assistant_id:
            client.beta.assistants.delete(created_assistant_id)
        if created_vector_store_id:
            client.beta.vector_stores.delete(created_vector_store_id)
        if created_thread_id:
            client.beta.threads.delete(created_thread_id)

    return {"writing_id": str(id), "writing": response}

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

async def add_resources_to_writing(writing_id, resource_type, resource_name, resource_description, resource_file):
    print(f"writing_id: {writing_id}")
    print(f"resource_type: {resource_type}")
    print(f"resource_name: {resource_name}")
    print(f"resource_description: {resource_description}")
    print(f"resource_file: {resource_file}")
    s3_file_manager = S3FileManager()
    atlas_client = AtlasClient()
    resource_id = ObjectId()
    key = f"qu-writing-design/{writing_id}/resources/{resource_id}.{resource_file.filename.split('.')[-1]}"
    await s3_file_manager.upload_file_from_frontend(resource_file, key)

    key = quote(key)
    resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"
    resource = {
        "resource_id": resource_id,
        "resource_type": resource_type,
        "resource_name": resource_name,
        "resource_description": resource_description,
        "resource_link": resource_link
    }

    atlas_client.update(
        collection_name="writing_design",
        filter={"_id": ObjectId(writing_id)},
        update={
            "$push": {
                "all_resources": resource
            }
        }
    )

    return resource

async def save_writing(writing_id, writing_outline, message, resources):
    resources = json.loads(resources)
    print(resources)
    atlas_client = AtlasClient()
    
    writing = atlas_client.find(collection_name="writing_design", filter={"_id": ObjectId(writing_id)})
    if not writing:
        return False
    writing = writing[0]
    history = writing.get("history", [])
    if not history:
        history={
                "writing_outline": writing_outline,
                "version": 1.0,
                "timestamp": datetime.datetime.now(),
                "feedback": message,
                "resources": resources
            }
    else:
        latest_version = history[-1]
        history={
                "writing_outline": writing_outline,
                "version": latest_version["version"] + 1.0,
                "timestamp": datetime.datetime.now(),
                "feedback": message,
                "resources": resources
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
    atlas_client.update(
        collection_name="writing_design",
        filter={"_id": ObjectId(writing_id)},
        update={
            "$set": {
                "writing_outline": writing_outline
            }
        }
    )
       
    return True

async def create_rewriting_project(writing_name, writing_description):
    atlas_client = AtlasClient()
    project_id = ObjectId()
    atlas_client.insert(
        collection_name="writing_design",
        document={
            "project_id": project_id,
            "writing_name": writing_name,
            "writing_description": writing_description,
            "status": "In Progress",
            "identifier": "rewriting"
        }
    )
    return project_id

async def rewrite_writing(writing_input):
    llm = LLM()
    print("Writing input", writing_input)

    prompt = _get_prompt("REWRITE_PROMPT")

    prompt = PromptTemplate(template=prompt, input_variables=["WRITING_INPUT", "USER_INSTRUCTIONS"])

    user_instructions = "Add the definition of cryptocurrency and the reference for the definition."

    inputs = {"WRITING_INPUT": writing_input, "USER_INSTRUCTIONS": user_instructions}

    response = llm.get_response(prompt, inputs)

    response = response.replace('```', '')

    return response
