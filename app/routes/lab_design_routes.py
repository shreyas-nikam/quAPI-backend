from app.services.lab_design_services import *
from fastapi import APIRouter, UploadFile, File, Form
from typing import List, Optional
from app.services.github_helper_functions import get_repo_issues

router = APIRouter()

# Endpoint for generating lab outline based on input files and instructions.
@router.post("/generate_lab_outline")
async def generate_lab_outline_api(files: List[List[UploadFile]] = File(...),
                                  instructions: str = Form(...),
                                  use_metaprompt: Optional[bool] = Form(False)
                                  ):
    return await generate_lab_outline(files, instructions, use_metaprompt=False) 

# Endpoint to clone an existing lab using the provided lab_id.
@router.post("/clone_lab")
async def clone_lab_api(lab_id: str = Form(...)):
    return await clone_lab(lab_id)

# Endpoint to delete an existing lab using lab_id.
@router.post("/delete_lab")
async def delete_lab_api(lab_id: str = Form(...)):
    return await delete_lab(lab_id)

# Endpoint to create a lab with details like username, lab name, description, outline, files, and lab image.
@router.post("/create_lab")
async def create_lab_api(username: str = Form(...), lab_name: str = Form(...),  lab_description: str = Form(...),
                         lab_outline: str = Form(...), files: Optional[List[UploadFile]] = File(None),
                         lab_image: UploadFile = File(...)):
    return await create_lab(username, lab_name, lab_description, lab_outline, files, lab_image)

# Endpoint to fetch labs associated with a username.
@router.post("/labs")
async def labs_api(username: str = Form(...)):
    return await get_labs(username)

# Endpoint to add resources to an existing lab.
@router.post("/add_resources_to_lab")
async def add_resources_to_lab_api(lab_id: str = Form(...), 
                                   resource_type: str = Form(...), 
                                   resource_name: str = Form(...), 
                                   resource_description: str = Form(...), 
                                   resource_file: Optional[UploadFile] = File(None)):
    return await add_resources_to_lab(lab_id, resource_type, resource_name, resource_description, resource_file)

# Endpoint to replace existing resources in a lab with new details.
@router.post("/replace_resources_in_lab")
async def replace_resources_in_lab_api(lab_id: str = Form(...), 
                                       resource_id: str = Form(...), 
                                       resource_type: str = Form(...), 
                                       resource_name: str = Form(...), 
                                       resource_description: str = Form(...), 
                                       resource_file: Optional[UploadFile] = File(None),
                                       lab_design_step: Optional[int] = Form(None)):
    return await replace_resources_in_lab(lab_id=lab_id, 
                                          resource_id=resource_id, 
                                          resource_type=resource_type, 
                                          resource_name=resource_name, 
                                          resource_description=resource_description, 
                                          resource_file=resource_file if resource_file else None, 
                                          lab_design_step=lab_design_step if lab_design_step else 0)

# Endpoint to delete a resource from a lab.
@router.post("/delete_resources_from_lab")
async def delete_resources_from_lab_api(lab_id: str = Form(...), resource_id: str = Form(...)):
    return await delete_resources_from_lab(lab_id, resource_id)

# Endpoint to get details of a specific lab using lab_id.
@router.get("/get_lab/{lab_id}")
async def get_lab_api(lab_id: str):
    return await get_lab(lab_id)

# Endpoint to generate an idea for a concept lab using lab_id, instructions, and a prompt.
@router.post("/generate_idea_for_concept_lab")
async def generate_idea_for_concept_lab_api(lab_id: str = Form(...), instructions: str = Form(...),
                                            prompt: str = Form(...), use_metaprompt: Optional[bool] = Form(False)):
    return await generate_idea_for_concept_lab(lab_id, instructions, prompt, use_metaprompt=False)

# Endpoint to generate a business use case for a lab using lab_id and a prompt.
@router.post("/generate_business_use_case_for_lab")
async def generate_business_use_case_for_lab_api(lab_id: str = Form(...), prompt: str = Form(...),
                                                 use_metaprompt: Optional[bool] = Form(False)):
    return await generate_business_use_case_for_lab(lab_id, prompt, use_metaprompt)

# Endpoint to generate technical specifications for a lab using lab_id and a prompt.
@router.post("/generate_technical_specifications_for_lab")
async def generate_technical_specifications_for_lab_api(lab_id: str = Form(...), prompt: str = Form(...),
                                                        use_metaprompt: Optional[bool] = Form(False)):
    return await generate_technical_specifications_for_lab(lab_id, prompt, use_metaprompt=False)

# Endpoint to regenerate content with user provided feedback.
@router.post("/regenerate_with_feedback")
async def regenerate_with_feedback_api(content: str = Form(...), feedback: str = Form(...),
                                       use_metaprompt: Optional[bool] = Form(False)):
    return await regenerate_with_feedback(content, feedback, use_metaprompt=False)

# Endpoint to save a concept lab idea to the lab.
@router.post("/save_concept_lab_idea")
async def save_concept_lab_idea_api(lab_id: str = Form(...), 
                                    idea: str = Form(...)):
    return await save_concept_lab_idea(lab_id, idea)

# Endpoint to save the business use case for a lab.
@router.post("/save_business_use_case")
async def save_business_use_case_api(lab_id: str = Form(...), 
                                     business_use_case: str = Form(...)):
    return await save_business_use_case(lab_id, business_use_case)

# Endpoint to save technical specifications for a lab.
@router.post("/save_technical_specifications")
async def save_technical_specifications_api(lab_id: str = Form(...), 
                                            technical_specifications: str = Form(...)):
    return await save_technical_specifications(lab_id, technical_specifications)

# Endpoint to convert lab markdown into a PDF, with an optional lab_design_step parameter.
@router.post("/convert_to_pdf_for_lab")
async def convert_to_pdf_for_lab_api(lab_id: str = Form(...), markdown: str = Form(...),
                                     template_name: str = Form(...), lab_design_step: Optional[int] = Form(None)):
    return await convert_to_pdf_for_lab(lab_id=lab_id, markdown=markdown,
                                        template_name=template_name, lab_design_step=lab_design_step if lab_design_step else 0)

# Endpoint to save lab instructions.
@router.post("/save_lab_instructions")
async def save_lab_instructions_api(lab_id: str = Form(...), 
                                    instructions: str = Form(...)):
    return await save_lab_instructions(lab_id, instructions)

# Endpoint to submit a lab for generation processing.
@router.post("/submit_lab_for_generation")
async def submit_lab_for_generation_api(lab_id: str = Form(...)):
    return await submit_lab_for_generation(lab_id, "in_lab_generation_queue")

# Endpoint to create a GitHub issue for lab
@router.post("/create_github_issue")
async def create_github_issue_api(
    lab_id: str = Form(...),
    issue_title: str = Form(...),
    issue_description: str = Form(...),
    labels: Optional[List[str]] = Form(None),
    uploaded_files: Optional[List[UploadFile]] = Form(None)
):
    # Create a GitHub issue with optional labels and uploaded files
    response = await create_github_issue_in_lab(
        lab_id, 
        issue_title, 
        issue_description, 
        labels=labels if labels else [],  # Use the provided labels or default to empty list
        uploaded_files=uploaded_files if uploaded_files else []  # Use the provided files or default to empty list
    )
    return response

# Endpoint to update the selected idea for a lab.
@router.post("/update_selected_idea")
async def update_selected_idea_api(lab_id: str = Form(...), index: int = Form(...)):
    return await update_selected_idea(lab_id, index)

@router.post("/update_lab_design_status")
async def update_lab_design_status_api(lab_id: str = Form(...), lab_design_status: str = Form(...)):
    return await update_lab_design_status(lab_id, lab_design_status)

# Endpoint to update lab ideas with new ones.
@router.post("/update_lab_ideas")
async def update_lab_ideas_api(lab_id: str = Form(...), lab_ideas: str = Form(...)):
    return await update_lab_ideas(lab_id, lab_ideas)

# Endpoint to fetch the lab ideas for a given lab.
@router.get("/get_lab_ideas/{lab_id}")
async def get_lab_ideas_api(lab_id: str):
    return await get_lab_ideas(lab_id)

# Endpoint to get lab prompt based on a provided prompt type.
@router.post("/lab_prompt")
async def labs_prompt_api(prompt_type: str = Form(...)):
    return await get_labs_prompt(prompt_type)

# Endpoint to update lab information including lab name and description.
@router.post("/update_lab_info")
async def update_lab_info_api(lab_id: str = Form(...), lab_name: str = Form(...),
                              lab_description: str = Form(...)):
    return await update_lab_info(lab_id, lab_name, lab_description)

# Endpoint to fetch GitHub issues for a lab.
@router.get("/get_lab_issues/{lab_id}")
async def get_lab_issues_api(lab_id: str):
    return await get_repo_issues(lab_id)