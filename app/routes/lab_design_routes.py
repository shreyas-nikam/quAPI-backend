from app.services.lab_design_services import *
from fastapi import APIRouter, UploadFile, File, Form
from typing import List, Optional

router = APIRouter()

# done
@router.post("/generate_lab_outline")
async def generate_lab_outline_api(files: List[UploadFile] = File(...),
                                  instructions: str = Form(...)):
    return await generate_lab_outline(files, instructions) 

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
async def create_lab_api(lab_name: str = Form(...),  lab_description: str = Form(...), lab_outline: str = Form(...), files: Optional[UploadFile] = File(None), lab_image: UploadFile = File(...)):
    return await create_lab(lab_name, lab_description, lab_outline, files, lab_image)

# working
@router.get("/labs")
async def labs_api():
    return await get_labs()

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


@router.post("/generate_business_use_case_for_lab")
async def generate_business_use_case_for_lab_api(lab_id: str = Form(...), instructions: str = Form(...)):
    return await generate_business_use_case_for_lab(lab_id, instructions)

@router.post("/generate_technical_specifications_for_lab")
async def generate_technical_specifications_for_lab_api(lab_id: str = Form(...)):
    return await generate_technical_specifications_for_lab(lab_id)

@router.post("/regenerate_with_feedback")
async def regenerate_with_feedback_api(content: str=Form(...), feedback: str = Form(...)):
    return await regenerate_with_feedback(content, feedback)


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

# done
@router.post("/submit_lab_for_content_generation")
async def submit_lab_for_content_generation_api(lab_id: str = Form(...), instructions: str = Form(...)):
    return await submit_lab_for_step(lab_id, 1, "in_content_generation_queue", instructions)

# done
@router.post("/submit_lab_for_structure_generation")
async def submit_lab_for_structure_generation_api(lab_id: str = Form(...)):
    return await submit_lab_for_step(lab_id, 4, "in_structure_generation_queue")

# done
@router.post("/submit_lab_for_deliverables_generation")
async def submit_lab_for_deliverables_generation_api(lab_id: str = Form(...)):
    return await submit_lab_for_step(lab_id, 7, "in_deliverables_generation_queue")

# done
@router.post("/submit_for_publishing_pipeline")
async def submit_for_publishing_pipeline_api(lab_id: str = Form(...)):
    return await submit_lab_for_step(lab_id, 9, "in_publishing_queue")

# done
@router.post("/fetch_note")
async def fetch_note_api(url: str = Form(...)):
    return await fetch_note(url)

# done
@router.post("/fetch_quizdata")
async def fetch_quizdata_api(url: str = Form(...)):
    return await fetch_quizdata(url)