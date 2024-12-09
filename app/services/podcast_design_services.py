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
import concurrent.futures as cf
import io
from tempfile import NamedTemporaryFile  # Import for temporary file creation
from pathlib import Path  # Import Path for handling filesystem paths
import tempfile
import boto3

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

# Voice mapping for speakers
VOICE_MAP = {
    "female-1": "alloy",
    "male-1": "onyx",
    "female-2": "shimmer",
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

def _get_file_type(file: UploadFile):
    if file.content_type.startswith("image"):
        return "Image"
    elif file.content_type.startswith("text"):
        return "Note"
    else:
        return "File"

def save_response_to_file(response, filename="podcast_output.txt"):
    """
    Save the given response to a text file.
    
    :param response: The string content to save.
    :param filename: The name of the file to save the content into.
    """
    try:
        with open(filename, "w", encoding="utf-8") as file:
            file.write(response)
    except Exception as e:
        logger.error(f"Failed to save response to file: {e}")

def format_podcast_dialogue(response_text):
    """
    Formats podcast dialogue for display in a markdown editor with a single blank line between each speaker's dialogue.

    Args:
        response_text (str): The raw response text containing the podcast dialogue.

    Returns:
        str: The formatted podcast dialogue with proper markdown styling.
    """
    formatted_lines = []
    lines = response_text.split("\n")

    for line in lines:
        # Check if the line contains a speaker label followed by content
        if ":" in line:
            speaker, content = line.split(":", 1)
            # Correctly format the speaker's name (bold) and content
            formatted_lines.append(f"**{speaker.strip()}**: {content.strip()}")
        elif line.strip():  # Add non-empty lines as-is
            formatted_lines.append(line.strip())

    # Join all lines with a blank line in between for better readability in markdown
    return "\n\n".join(formatted_lines)



async def generate_podcast_outline(files, instructions):
    podcast_prompt = _get_prompt("GENERATE_PODCAST_WITH_TEXT_PROMPT")
    podcast_prompt = podcast_prompt.replace("{metadeta}", instructions)

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
        return """ **Alex:** Welcome, everyone, to *Decoding AI: A Revolution in Business and National Security*! I'm your host, Alex Johnson, and today, we're diving into the fascinating world of artificial intelligence with a leading expert, Dr. Anya Sharma. **Anya:** Thanks for having me, Alex. It's exciting to discuss this rapidly evolving field. **Alex:** Absolutely! For those just tuning in, can you give us a quick, jargon-free definition of artificial intelligence and machine learning? **Anya:** Certainly. Artificial intelligence, or AI, is essentially the ability of a computer to mimic human intelligence. That includes problem-solving, decision-making, and learning from experience. Machine learning, or ML, is a subset of AI. It’s where we teach computers to learn from data without explicit programming—they learn patterns and make predictions based on that data. **Alex:** So, essentially, it's like teaching a computer to learn by example, rather than giving it a set of strict rules to follow? **Anya:** Exactly! That’s a huge shift from how computers have worked for the past 75 years. Think about it—before AI, we programmed every single step a computer took. Now, we can train a system to learn and adapt on its own, leading to some pretty amazing capabilities. **Alex:** That’s fascinating. Can you explain this difference using an analogy? **Anya:** Sure. Imagine explaining computers in 1950 to someone using slide rules and manual calculators. You tell them about machines that can do complex calculations instantly, learn, and adapt—they’d be amazed! That’s where we are now with AI—a complete game-changer impacting everything from business to defense. **Alex:** What exactly can AI do these days? And just as importantly, what can’t it do? **Anya:** AI excels at tasks involving massive data sets, like natural language processing, computer vision, and anomaly detection. It’s transforming industries—think self-driving cars, medical diagnoses, and fraud detection. But AI has limitations: it struggles with uncertainty, explaining its reasoning, and handling unexpected situations or genuine creativity. **Alex:** Let’s delve into specific applications. How is AI impacting business? **Anya:** AI is revolutionizing industries. It assists humans in programming and decision-making, streamlines supply chains, optimizes marketing, and enhances customer support. In healthcare, it’s helping with diagnostics, drug discovery, and personalized medicine. Autonomous vehicles and human-machine teaming are other key areas of transformation. **Alex:** And in national security? How is AI reshaping warfare and intelligence? **Anya:** AI is transforming national security with enhanced surveillance, autonomous systems, and efficient data analysis. It plays a crucial role in human-machine teaming, augmenting intelligence while keeping humans at the decision-making helm. However, ethical concerns arise, especially regarding autonomous weapons and AI-driven disinformation. **Alex:** Those are critical points. Let’s talk about the hardware driving these advancements. What’s happening on that front? **Anya:** Hardware is crucial. Specialized AI chips, cloud computing, and robust infrastructure are propelling the field forward. Companies like Nvidia lead the way, with a significant software advantage that creates a competitive edge. However, challenges remain as newer players work to catch up. **Alex:** This field is moving at lightning speed. To wrap things up, what are the key takeaways? **Anya:** AI is a revolutionary force transforming business and national security. While its potential is immense, so are its challenges. Responsible development, ethical considerations, and informed usage are critical. This is a rapidly evolving field, so staying informed is essential. **Alex:** Dr. Sharma, thank you for sharing your expertise. And to our listeners, thank you for tuning in to *Decoding AI*. Until next time, keep exploring and stay curious! """
    finally:
        # Clean up all created resources to avoid charges
        if created_assistant_id:
            client.beta.assistants.delete(created_assistant_id)
        if created_vector_store_id:
            client.beta.vector_stores.delete(created_vector_store_id)
        if created_thread_id:
            client.beta.threads.delete(created_thread_id)

    dialogue_prompt = _get_prompt("EXTRACT_DIALOGUE_FROM_CONTENT")
    dialogue_prompt = podcast_prompt.replace("{text}", response)
    try:
        response = await generate_podcast_dialogue(dialogue_prompt)
        formatted_response = format_podcast_dialogue(response)
        return formatted_response
    
    except Exception as e:
        logging.error(f"Error in generating podcast dialogue: {e}")
        return response

    return response




async def generate_podcast_dialogue(dialogue, files = None):
    podcast_prompt = _get_prompt("EXTRACT_DIALOGUE_FROM_CONTENT")
    podcast_prompt = podcast_prompt.replace("{text}", dialogue)

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
        return """ **Alex:** Welcome, everyone, to *Decoding AI: A Revolution in Business and National Security*! I'm your host, Alex Johnson, and today, we're diving into the fascinating world of artificial intelligence with a leading expert, Dr. Anya Sharma. **Anya:** Thanks for having me, Alex. It's exciting to discuss this rapidly evolving field. **Alex:** Absolutely! For those just tuning in, can you give us a quick, jargon-free definition of artificial intelligence and machine learning? **Anya:** Certainly. Artificial intelligence, or AI, is essentially the ability of a computer to mimic human intelligence. That includes problem-solving, decision-making, and learning from experience. Machine learning, or ML, is a subset of AI. It’s where we teach computers to learn from data without explicit programming—they learn patterns and make predictions based on that data. **Alex:** So, essentially, it's like teaching a computer to learn by example, rather than giving it a set of strict rules to follow? **Anya:** Exactly! That’s a huge shift from how computers have worked for the past 75 years. Think about it—before AI, we programmed every single step a computer took. Now, we can train a system to learn and adapt on its own, leading to some pretty amazing capabilities. **Alex:** That’s fascinating. Can you explain this difference using an analogy? **Anya:** Sure. Imagine explaining computers in 1950 to someone using slide rules and manual calculators. You tell them about machines that can do complex calculations instantly, learn, and adapt—they’d be amazed! That’s where we are now with AI—a complete game-changer impacting everything from business to defense. **Alex:** What exactly can AI do these days? And just as importantly, what can’t it do? **Anya:** AI excels at tasks involving massive data sets, like natural language processing, computer vision, and anomaly detection. It’s transforming industries—think self-driving cars, medical diagnoses, and fraud detection. But AI has limitations: it struggles with uncertainty, explaining its reasoning, and handling unexpected situations or genuine creativity. **Alex:** Let’s delve into specific applications. How is AI impacting business? **Anya:** AI is revolutionizing industries. It assists humans in programming and decision-making, streamlines supply chains, optimizes marketing, and enhances customer support. In healthcare, it’s helping with diagnostics, drug discovery, and personalized medicine. Autonomous vehicles and human-machine teaming are other key areas of transformation. **Alex:** And in national security? How is AI reshaping warfare and intelligence? **Anya:** AI is transforming national security with enhanced surveillance, autonomous systems, and efficient data analysis. It plays a crucial role in human-machine teaming, augmenting intelligence while keeping humans at the decision-making helm. However, ethical concerns arise, especially regarding autonomous weapons and AI-driven disinformation. **Alex:** Those are critical points. Let’s talk about the hardware driving these advancements. What’s happening on that front? **Anya:** Hardware is crucial. Specialized AI chips, cloud computing, and robust infrastructure are propelling the field forward. Companies like Nvidia lead the way, with a significant software advantage that creates a competitive edge. However, challenges remain as newer players work to catch up. **Alex:** This field is moving at lightning speed. To wrap things up, what are the key takeaways? **Anya:** AI is a revolutionary force transforming business and national security. While its potential is immense, so are its challenges. Responsible development, ethical considerations, and informed usage are critical. This is a rapidly evolving field, so staying informed is essential. **Alex:** Dr. Sharma, thank you for sharing your expertise. And to our listeners, thank you for tuning in to *Decoding AI*. Until next time, keep exploring and stay curious! """
    finally:
        # Clean up all created resources to avoid charges
        if created_assistant_id:
            client.beta.assistants.delete(created_assistant_id)
        if created_vector_store_id:
            client.beta.vector_stores.delete(created_vector_store_id)
        if created_thread_id:
            client.beta.threads.delete(created_thread_id)

    return response

async def get_podcasts():
    try:
        atlas_client = AtlasClient()
        
        # Attempt to retrieve podcasts
        podcasts = atlas_client.find("podcast_design")

        # Ensure ObjectIds are converted to strings
        podcasts = _convert_object_ids_to_strings(podcasts)
      
        return podcasts

    except ConnectionError as ce:
        # Handle connection errors
        return {"error": "Failed to connect to the database. Please try again later."}

    except ValueError as ve:
        # Handle data conversion issues
        return {"error": "Data format issue encountered while processing podcasts."}

    except Exception as e:
        # Catch-all for any other unexpected exceptions
        return {"error": "An unexpected error occurred. Please contact support."}

async def generate_audio_for_podcast(outline_text: str, podcast_id: str):
    """
    Generate audio based on the provided podcast outline text, save it as an MP3 file,
    and upload to S3.
    
    Args:
        outline_text (str): The transcript to generate audio from.
        podcast_id (str): The podcast ID used for creating the S3 key.
    
    Returns:
        str: The URL to the uploaded MP3 file.
        str: Transcript used for generating the audio.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_KEY"))
    
    audio = b""  # Initialize the audio data as an empty byte string
    transcript = outline_text.strip()  # Use the provided outline as the transcript

    # Generate audio for each line in the transcript
    with cf.ThreadPoolExecutor() as executor:
        futures = []
        # Detect the number of speakers (assuming 2 for this case)
        speaker_voices = random.sample(list(VOICE_MAP.values()), 2)  # Randomly select two voices
        
        for i, line in enumerate(transcript.split("\n")):
            line = line.strip()
            if line:  # Ignore empty lines
                # Alternate between the two voices
                voice = speaker_voices[i % 2]  # Alternate between two voices
                future = executor.submit(get_mp3, line, voice)
                futures.append((future, line))
        
        # Collect the audio chunks from each future
        for future, line in futures:
            audio_chunk = future.result()
            audio += audio_chunk


    s3_file_manager = S3FileManager()

    audio_key = f"qu-podcast-design/{podcast_id}/podcast_audio/podcast_audio_{int(time.time())}.mp3"
    
    # Use the save_mp3_and_upload method to save the file locally and then upload it to S3
    try:
        await s3_file_manager.save_mp3_and_upload(audio, audio_key)
    except Exception as e:
        logging.error(f"Failed to upload the file to S3 with key: {audio_key}")
        return None, transcript

    # Log success
    logging.info(f"File uploaded to S3 with key: {audio_key}")

    # Make the uploaded file public
    s3_file_manager.make_object_public(audio_key)

    # Generate the S3 URL for the uploaded audio
    audio_key = quote(audio_key)
    podcast_audio_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{audio_key}"

    return podcast_audio_link, transcript

def get_mp3(text: str, voice: str) -> bytes:
    """
    Generate MP3 audio for the given text and voice using the OpenAI API.
    """
    client = OpenAI(api_key=os.getenv("OPENAI_KEY"))
    with client.audio.speech.with_streaming_response.create(
        model="tts-1",
        voice=voice,
        input=text,
    ) as response:
        with io.BytesIO() as file:
            for chunk in response.iter_bytes():
                file.write(chunk)
            return file.getvalue()

async def create_podcast(podcast_name, podcast_description, podcast_transcript, files, podcast_image):
    podcast_status = "In Design Phase"

    s3_file_manager = S3FileManager()
    atlas_client = AtlasClient()

    # Upload the podcast image to S3 and get the link
    podcast_id = ObjectId()
    key = f"qu-podcast-design/{podcast_id}/podcast_image/{podcast_image.filename}"
    await s3_file_manager.upload_file_from_frontend(podcast_image, key)
    key = quote(key)
    podcast_image_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{key}"

    # Generate podcast audio and get the link
    podcast_audio_link, _ = await generate_audio_for_podcast(podcast_transcript, str(podcast_id))

    if not podcast_audio_link:
        logging.error("Failed to generate podcast audio.")
        return None

    podcast = {
        "_id": podcast_id,
        "podcast_name": podcast_name,
        "podcast_description": podcast_description,
        "podcast_image": podcast_image_link,
        "podcast_transcript": podcast_transcript,
        "status": podcast_status,
        "podcast_audio": podcast_audio_link  # Add the audio link here
    }
    
    step_directory = PODCAST_DESIGN_STEPS[0]

    raw_resources = []
    if files:
        for file in files:
            resource_type = _get_file_type(file)

            key = f"qu-podcast-design/{podcast_id}/{step_directory}/{file.filename}"
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

    podcast[step_directory] = raw_resources

    # Insert the podcast into the database
    atlas_client.insert("podcast_design", podcast)

    # Convert object IDs to strings for the response
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

async def delete_podcast(podcast_id):

    atlas_client = AtlasClient()
    podcast = atlas_client.find("podcast_design", filter={
                               "_id": ObjectId(podcast_id)})

    if not podcast:
        return "Podcast not found"

    podcast = podcast[0]

    atlas_client.delete("podcast_design", filter={"_id": ObjectId(podcast_id)})

    podcast = _convert_object_ids_to_strings(podcast)

    return podcast
