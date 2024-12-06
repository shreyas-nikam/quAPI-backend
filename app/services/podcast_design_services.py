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


PODCAST_DESIGN_STEPS = [
    "raw_resources",  # automatic
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

async def generate_podcast_outline(files, instructions):


    podcast_prompt = _get_prompt("GENERATE_PODCAST_WITH_TEXT_PROMPT")
    podcast_prompt = podcast_prompt.replace("{metadeta}", instructions)
    print("Podcast prompt is: ", podcast_prompt)

    # return "**Podcast Title: AI and Machine Learning in Finance** --- **Intro Music Fades In** **Host 1: Alex** Welcome to “AI and Machine Learning in Finance,” the show where we unpack how cutting-edge technology is revolutionizing the world of finance. I’m your host, Alex. **Host 2: Jamie** And I’m Jamie! Today, we’re diving deep into the fascinating world of AI and ML, highlighting some fundamental concepts while also exploring their real-world applications in the finance sector. **Alex** So, Jamie, let’s start with the basics. Can you explain what AI and ML actually are, and how they differ? **Jamie** Absolutely, Alex! Artificial Intelligence, or AI, refers to the simulation of human intelligence in machines. These machines are programmed to think and learn like humans. Machine Learning, a subset of AI, is all about algorithms that improve automatically through experience. In simple terms, ML allows computers to learn from data and get better over time without being explicitly programmed to do so. **Alex** That makes sense! It's like teaching a child how to solve puzzles; the more puzzles they solve, the better they become at it. **Jamie** Exactly! And when we apply these technologies in finance, it gets really exciting. For instance, institutions use AI for fraud detection. By analyzing huge amounts of transaction data, machine learning models can spot unusual patterns that may indicate fraudulent activity far quicker than a human could. **Alex** I love that. It’s like having a digital watchdog that never sleeps, right? Speaking of which, what are some other fascinating applications of AI and ML in finance? **Jamie** Oh, the list is extensive. One key application is in algorithmic trading. AI systems can analyze market data and make trades at lightning speeds—much faster than any human trader. They can also react to news and events in real-time, which is invaluable in a market that moves as fast as today’s does. **Alex** That raises an interesting point about risk management. How does AI help in that area? **Jamie** Good question! AI and ML help quantify risks by analyzing historical data and forecasting financial outcomes based on various scenarios. This capability enables financial institutions to make more informed decisions about lending, investments, and even compliance with regulatory standards. **Alex** That’s pretty powerful! I can only imagine how it must feel for risk managers to have these tools at their fingertips. But tell me, what are the challenges of implementing AI in finance? **Jamie** There definitely are challenges. One significant issue is data quality. AI models rely heavily on data, so if that data is inaccurate or incomplete, it can lead to poor decision-making. Additionally, there are regulatory concerns and the need for transparency. Many financial firms are also navigating the talent shortage in data science and AI specialists. **Alex** And with such rapidly evolving technology, keeping pace with advancements must be a challenge as well. **Jamie** Definitely. It’s a double-edged sword; the technology moves fast, and firms need to adapt quickly or risk becoming obsolete. Coupled with ethical considerations—like bias in AI models—there's a lot for firms to juggle. **Alex** Speaking of ethics, that sounds like a juicy topic! Let’s pivot a bit. Can you share an anecdote or an example of how AI failure has caused hurdles for financial institutions? **Jamie** Sure! One major example is the infamous “robo-advisor,” which aimed to automate investment management. While they’re useful, some algorithms accidentally favored certain market segments over others, leading to poorly diversified portfolios for clients. This sparked a backlash and raised questions about how much trust we should put in machine-generated advice. **Alex** That’s fascinating and somewhat alarming! It really emphasizes the need for human oversight, doesn’t it? **Jamie** Absolutely. While AI can enhance efficiency, human intuition and experience are irreplaceable. A balance between leveraging AI and human judgment will lead to the best results. **Alex** As we wrap up this enlightening discussion, what would you say are the main takeaways for our listeners today about AI and ML in finance? **Jamie** Well, listeners, remember that AI and ML aren’t just buzzwords; they are transformative technologies that can optimize operations, manage risks, and detect fraud effectively. However, it’s essential to be aware of the challenges, including data quality and ethical implications. Incorporating AI in finance isn’t about replacing human intelligence but augmenting it. **Alex** Very well said, Jamie! It’s clear that embracing AI in finance requires a thoughtful approach. Thank you all for tuning in! **Jamie** And don’t forget to join us next time, where we’ll explore the future of AI and its potential in revolutionizing customer service in the finance world! **Alex** Until next time, stay curious and keep learning! **Outro Music Fades In** --- **End of Podcast**"
    # return "Podcast outline generated successfully"
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
            name="podcast creator",
            instructions=podcast_prompt,
            model=os.getenv("OPENAI_MODEL"),
            tools=[{"type": "file_search"}]
        )
        created_assistant_id = assistant.id  # Track the assistant

        vector_store = client.beta.vector_stores.create(
            name="Podcast Resources",
            expires_after={"days": 1, "anchor": "last_active_at"},
        )
        created_vector_store_id = vector_store.id  # Track the vector store
        if files:
            file_batch = client.beta.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vector_store.id, files=assistant_files_streams
            )

            assistant = client.beta.assistants.update(
                assistant_id=assistant.id,
                tool_resources={"file_search": {
                    "vector_store_ids": [vector_store.id]}},
            )

        else:
            assistant = client.beta.assistants.update(
                assistant_id=assistant.id,
            )

        thread = client.beta.threads.create(
            messages=[{
                "role": "user",
                "content": "Create the podcast based on the instructions provided and the following user's instructions: " + instructions,
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

    print("Response is: ", response)
    return response

# async def get_podcasts():
#     atlas_client = AtlasClient()
#     podcasts = atlas_client.find("podcast_design")
#     podcasts = _convert_object_ids_to_strings(podcasts)
#     print("Podcasts are: ", podcasts)
#     return podcasts

async def get_podcasts():
    try:
        atlas_client = AtlasClient()
        
        # Attempt to retrieve podcasts
        podcasts = atlas_client.find("podcast_design")

        print("Podcasts are: ", podcasts)
        # Ensure ObjectIds are converted to strings
        podcasts = _convert_object_ids_to_strings(podcasts)
        
        # Print the retrieved podcasts for debugging
      
        return podcasts

    except ConnectionError as ce:
        # Handle connection errors
        print(f"Connection error while fetching podcasts: {ce}")
        return {"error": "Failed to connect to the database. Please try again later."}

    except ValueError as ve:
        # Handle data conversion issues
        print(f"Value error during podcast processing: {ve}")
        return {"error": "Data format issue encountered while processing podcasts."}

    except Exception as e:
        # Catch-all for any other unexpected exceptions
        print(f"Unexpected error: {e}")
        return {"error": "An unexpected error occurred. Please contact support."}


async def create_podcast(podcast_name, podcast_description, podcast_transcript, files, podcast_image):
    podcast_status = "In Design Phase"

    s3_file_manager = S3FileManager()
    atlas_client = AtlasClient()
   

    # upload the podcast image to s3 and get the link
    podcast_id = ObjectId()
    key = f"qu-podcast-design/{podcast_id}/podcast_image/{podcast_image.filename}"
    await s3_file_manager.upload_file_from_frontend(podcast_image, key)
    key = quote(key)
    podcast_image_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

    podcast = {
        "_id": podcast_id,
        "podcast_name": podcast_name,
        "podcast_description": podcast_description,
        "podcast_image": podcast_image_link,
        "podcast_transcript": podcast_transcript,
        "status": podcast_status
    }
    step_directory = PODCAST_DESIGN_STEPS[0]

    raw_resources = []
    if files:
        for file in files:
            resource_type = _get_file_type(file)

            key = f"qu-podcast-design/{podcast_id}/{
                step_directory}/{file.filename}"
            await s3_file_manager.upload_file_from_frontend(file, key)
            key = quote(key)
            resource_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{
                key}"

            raw_resources += [{
                "resource_id": ObjectId(),
                "resource_type": resource_type,
                "resource_name": file.filename,
                "resource_description": "",
                "resource_link": resource_link
            }]

    podcast[step_directory] = raw_resources

    atlas_client.insert("podcast_design", podcast)

    podcast = _convert_object_ids_to_strings(podcast)
    return podcast

async def get_podcast(podcast_id):

    atlas_client = AtlasClient()
    podcast = atlas_client.find("podcast_design", filter={
                               "_id": ObjectId(podcast_id)})

    if not podcast:
        return {}

    podcast = _convert_object_ids_to_strings(podcast)
    podcast = podcast[0]
    return podcast

