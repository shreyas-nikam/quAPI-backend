from app.services.lab_design_services import *
from fastapi import APIRouter, UploadFile, File, Form
from typing import List, Optional

router = APIRouter()

# done
@router.post("/generate_lab_outline")
async def generate_lab_outline_api(files: List[List[UploadFile]] = File(...),
                                  instructions: str = Form(...),
                                  use_metaprompt: Optional[bool] = Form(False)
                                  ):
    return await generate_lab_outline(files, instructions, use_metaprompt) 

# /clone_course -> takes in the course_id, course_name, course_image, course_description, and clones the course
@router.post("/clone_lab")
async def clone_lab_api(lab_id: str = Form(...)):
    return await clone_lab(lab_id)

# done
@router.post("/delete_lab")
async def delete_lab_api(lab_id: str = Form(...)):
    return await delete_lab(lab_id)

# working
@router.post("/create_lab")
async def create_lab_api(username: str = Form(...), lab_name: str = Form(...),  lab_description: str = Form(...), lab_outline: str = Form(...), files: Optional[List[UploadFile]] = File(None), lab_image: UploadFile = File(...)):
    return await create_lab(username, lab_name, lab_description, lab_outline, files, lab_image)

# working
@router.post("/labs")
async def labs_api(username: str = Form(...)):
    return await get_labs(username)

# done
@router.post("/add_resources_to_lab")
async def add_resources_to_lab_api(lab_id: str = Form(...), 
                                      resource_type: str = Form(...), 
                                      resource_name: str = Form(...), 
                                      resource_description: str = Form(...), 
                                      resource_file: Optional[UploadFile] = File(None) ):
    return await add_resources_to_lab(lab_id, resource_type, resource_name, resource_description, resource_file)

# done
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

# done - yet to test with frontend
@router.post("/delete_resources_from_lab")
async def delete_resources_from_lab_api(lab_id: str = Form(...), resource_id: str = Form(...)):
    return await delete_resources_from_lab(lab_id, resource_id)

# working
@router.get("/get_lab/{lab_id}")
async def get_lab_api(lab_id: str):
    return await get_lab(lab_id)

@router.post("/generate_idea_for_concept_lab")
async def generate_idea_for_concept_lab_api(lab_id: str = Form(...), instructions: str = Form(...), use_metaprompt: Optional[bool] = Form(False)):
    return await generate_idea_for_concept_lab(lab_id, instructions, use_metaprompt)

@router.post("/generate_business_use_case_for_lab")
async def generate_business_use_case_for_lab_api(lab_id: str = Form(...), use_metaprompt: Optional[bool] = Form(False)):
    return await generate_business_use_case_for_lab(lab_id, use_metaprompt)

@router.post("/generate_technical_specifications_for_lab")
async def generate_technical_specifications_for_lab_api(lab_id: str = Form(...), use_metaprompt: Optional[bool] = Form(False)):
    return await generate_technical_specifications_for_lab(lab_id, use_metaprompt)

@router.post("/regenerate_with_feedback")
async def regenerate_with_feedback_api(content: str=Form(...), feedback: str = Form(...), use_metaprompt: Optional[bool] = Form(False)):
    return await regenerate_with_feedback(content, feedback, use_metaprompt)

@router.post("/save_concept_lab_idea")
async def save_concept_lab_idea_api(lab_id: str = Form(...), 
                           idea: str = Form(...)):
    return await save_concept_lab_idea(lab_id, idea)

@router.post("/save_business_use_case")
async def save_business_use_case_api(lab_id: str = Form(...), 
                           business_use_case: str = Form(...)):
    return await save_business_use_case(lab_id, business_use_case)

@router.post("/save_technical_specifications")
async def save_technical_specifications_api(lab_id: str = Form(...), 
                           technical_specifications: str = Form(...)):
    return await save_technical_specifications(lab_id, technical_specifications)

@router.post("/convert_to_pdf_for_lab")
async def convert_to_pdf_for_lab_api(lab_id: str = Form(...), markdown: str = Form(...), template_name: str = Form(...), lab_design_step: Optional[int] = Form(None)):
    return await convert_to_pdf_for_lab(lab_id=lab_id, markdown=markdown, template_name=template_name, lab_design_step=lab_design_step if lab_design_step else 0)

@router.post("/save_lab_instructions")
async def save_lab_instructions_api(lab_id: str = Form(...), 
                           instructions: str = Form(...)):
    return await save_lab_instructions(lab_id, instructions)

@router.post("/submit_lab_for_generation")
async def submit_lab_for_generation_api(lab_id: str = Form(...)):
    return await submit_lab_for_generation(lab_id, "in_lab_generation_queue")

@router.post("/create_github_issue")
async def create_github_issue_api(
    lab_id: str = Form(...),
    issue_title: str = Form(...),
    issue_description: str = Form(...),
    labels: Optional[List[str]] = Form(None),
    uploaded_files: Optional[List[UploadFile]] = Form(None)
):
    # Pass the form data values directly, not empty lists
    response = await create_github_issue_in_lab(
        lab_id, 
        issue_title, 
        issue_description, 
        labels=labels if labels else [],  # Use the provided labels or default to empty list
        uploaded_files=uploaded_files if uploaded_files else []  # Use the provided files or default to empty list
    )
    return response


