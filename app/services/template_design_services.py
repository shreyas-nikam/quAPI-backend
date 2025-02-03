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

async def get_templates():
    """
    Get all templates
    
    Returns:
    - list of templates
    """
    mongo_client = AtlasClient()

    templates = mongo_client.find("model_templates", {})

    redacted_templates = []
    
    for template in templates:
        redacted_templates.append({
            "_id": str(template["_id"]),
            "name": template["name"],
            "note": template["note"],
        })

    return redacted_templates


async def get_template_outline(template_id):
    """
    Get template outline
    
    Args:
    - template_id: str
    
    Returns:
    - template outline
    """
    mongo_client = AtlasClient()

    template_outline  = mongo_client.find("model_templates", {"_id": ObjectId(template_id)})

    return template_outline


async def save_template_data(template_id, template_data):
    """
    Save template data

    Args:
    - template_id: str
    - template_data: dict

    Returns:
    - None
    """

    # Steps:
    # 1. Create a new entry in the model_reports collection with the template_id and template_data
    # 2. Convert the table_data from the template_data into a string
    # 3. Create a report html file for the template_data
    # 4. Save the report html file to the s3 bucket
    # 5. Save the url of the report html file to the model_reports collection
    # 6. Return the report_id, template_id, name and the url of the report html file
    
async def get_template_reports(template_id):
    """
    Get template reports
    
    Args:
    - template_id: str
    
    Returns:
    - list of template reports
    """
    mongo_client = AtlasClient()

    reports = mongo_client.find("model_reports", {"template_id": template_id})

    redacted_reports = []
    
    for report in reports:
        redacted_reports.append({
            "_id": str(report["_id"]),
            "template_id": report["template_id"],
            "name": report["name"],
            "url": report["url"],
        })

    return redacted_reports

async def delete_report(template_id, report_id):
    """
    Delete report
    
    Args:
    - template_id: str
    - report_id: str
    
    Returns:
    - None
    """
    mongo_client = AtlasClient()

    report = mongo_client.find("model_reports", {"_id": ObjectId(report_id)})

    if report:
        mongo_client.delete("model_reports", {"_id": ObjectId(report_id)})
        return "Report deleted"
    else:
        return "Report not found"