from app.services.course_design_services import *
from fastapi import APIRouter, UploadFile, File, Form
from typing import List, Optional

router = APIRouter()

# done
@router.post("/generate_course_outline")
async def generate_course_outline_api(files: Optional[List[UploadFile]] = File(None),
                                  instructions: str = Form(...)):
    return await generate_course_outline(files, instructions) 

# /clone_course -> takes in the course_id, course_name, course_image, course_description, and clones the course
@router.post("/clone_course")
async def clone_course_api(course_id: str = Form(...)):
    return await clone_course(course_id)

# done
@router.post("/delete_course")
async def delete_course_api(course_id: str = Form(...)):
    return await delete_course(course_id)

# done
@router.post("/create_course")
async def create_course_api(course_name: str = Form(...),  course_description: str = Form(...), course_outline: str = Form(...), files: Optional[List[UploadFile]] = File(None), course_image: UploadFile = File(...), modulesAtCreation: bool = Form(True)):
    return await create_course(course_name, course_description, course_outline, files, course_image, modulesAtCreation)

# done
@router.get("/courses")
async def courses_api():
    return await get_courses()

# done
@router.post("/add_module")
async def add_module_api(course_id: str = Form(...), module_name: str = Form(...), module_description: str = Form(...)):
    return await add_module(course_id, module_name, module_description)

# done
@router.post("/add_resources_to_module")
async def add_resources_to_module_api(course_id: str = Form(...), 
                                      module_id: str = Form(...), 
                                      resource_type: str = Form(...), 
                                      resource_name: str = Form(...), 
                                      resource_description: str = Form(...), 
                                      resource_file: Optional[UploadFile] = File(None) ):
    return await add_resources_to_module(course_id, module_id, resource_type, resource_name, resource_description, resource_file)

# /replace_resources_in_module -> takes in the course_id, module_id, resource_id, resource_type, resource_name, resource_description, resource_link, and replaces the resource in the module and s3
@router.post("/replace_resources_in_module")
async def replace_resources_in_module_api(course_id: str = Form(...), 
                                          module_id: str = Form(...), 
                                          resource_id: str = Form(...), 
                                          resource_type: str = Form(...), 
                                          resource_name: str = Form(...), 
                                          resource_description: str = Form(...), 
                                          resource_file: Optional[UploadFile] = File(None),
                                          course_design_step: Optional[int] = Form(None)):
    return await replace_resources_in_module(course_id=course_id, 
                                             module_id=module_id, 
                                             resource_id=resource_id, 
                                             resource_type=resource_type, 
                                             resource_name=resource_name, 
                                             resource_description=resource_description, 
                                             resource_file=resource_file if resource_file else None, 
                                             course_design_step=course_design_step if course_design_step else 0)

# done - yet to test with frontend
@router.post("/delete_resources_from_module")
async def delete_resources_from_module_api(course_id: str = Form(...), module_id: str = Form(...), resource_id: str = Form(...)):
    return await delete_resources_from_module(course_id, module_id, resource_id)

# done
@router.get("/get_course/{course_id}")
async def get_course_api(course_id: str):
    return await get_course(course_id)

# /submit_module_for_content_generation -> takes in the course_id, module_id, and submits the module for content generation to the content_generation_queue
@router.post("/submit_module_for_content_generation")
async def submit_module_for_content_generation_api(course_id: str = Form(...), module_id: str = Form(...), instructions: str = Form(...)):
    return await submit_module_for_step(course_id, module_id, 1, "in_content_generation_queue", instructions)

# /submit_module_for_structure_generation -> takes in the course_id, module_id and the reviewed files and submits them for structure generation to the structure_generation_queue
@router.post("/submit_module_for_structure_generation")
async def submit_module_for_structure_generation_api(course_id: str = Form(...), module_id: str = Form(...)):
    return await submit_module_for_step(course_id, module_id, 4, "in_structure_generation_queue")

# /submit_module_for_deliverables_generation -> takes in the course_id, module_id and the reviewed files and submits them for final generation to the deliverables_generation_queue
@router.post("/submit_module_for_deliverables_generation")
async def submit_module_for_deliverables_generation_api(course_id: str = Form(...), module_id: str = Form(...)):
    return await submit_module_for_step(course_id, module_id, 7, "in_deliverables_generation_queue")

# /submit_for_publishing_pipeline -> takes in the course_id and submits the course for the publishing pipeline
@router.post("/submit_for_publishing_pipeline")
async def submit_for_publishing_pipeline_api(course_id: str = Form(...), module_id: str = Form(...)):
    return await submit_module_for_step(course_id, module_id, 9, "in_publishing_queue")

# done
@router.post("/fetch_note")
async def fetch_note_api(url: str = Form(...)):
    return await fetch_note(url)

# done
@router.post("/fetch_quizdata")
async def fetch_quizdata_api(url: str = Form(...)):
    return await fetch_quizdata(url)

@router.post("/fetch_pdf")
async def fetch_pdf_api(url: str = Form(...)):
    return await fetch_pdf(url)
