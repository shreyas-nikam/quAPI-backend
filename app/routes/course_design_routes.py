from app.services.course_design_services import *
from fastapi import APIRouter, UploadFile, File, Form
from typing import List, Optional

router = APIRouter()

# done
@router.post("/generate_course_outline")
async def generate_course_outline_api(files: Optional[List[UploadFile]] = File(None),
                                  instructions: str = Form(...), prompt: str = Form(...)):
    return await generate_course_outline(files, instructions, prompt) 

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
async def create_course_api(username: str = Form(...),course_name: str = Form(...),  course_description: str = Form(...), course_outline: str = Form(...), files: Optional[List[UploadFile]] = File(None), course_image: UploadFile = File(...), modulesAtCreation: bool = Form(True)):
    return await create_course(username, course_name, course_description, course_outline, files, course_image, modulesAtCreation)

@router.post("/update_course_info")
async def update_course_info_api(course_id: str = Form(...), course_name: str = Form(...),  course_description: str = Form(...), course_outline: str = Form(...)):
    return await update_course_info(course_id, course_name, course_description, course_outline)

# done
@router.post("/courses")
async def courses_api(username: str = Form(...)):
    return await get_courses(username)

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

@router.get("/outline_prompt")
async def course_outline_prompt_api():
    return await course_outline_prompt()

@router.post("/submit_module_for_outline_generation")
async def submit_module_for_outline_generation_api(course_id: str = Form(...), module_id: str = Form(...), instructions: str = Form(...)):
    return await submit_module_for_step(course_id, module_id, 1, "in_outline_generation_queue", instructions)

# /submit_module_for_content_generation -> takes in the course_id, module_id, and submits the module for content generation to the content_generation_queue
@router.post("/submit_module_for_content_generation")
async def submit_module_for_content_generation_api(course_id: str = Form(...), module_id: str = Form(...)):
    return await submit_module_for_step(course_id, module_id, 4, "in_content_generation_queue")

# /submit_module_for_structure_generation -> takes in the course_id, module_id and the reviewed files and submits them for structure generation to the structure_generation_queue
@router.post("/submit_module_for_structure_generation")
async def submit_module_for_structure_generation_api(course_id: str = Form(...), module_id: str = Form(...)):
    return await submit_module_for_step(course_id, module_id, 7, "in_structure_generation_queue")

# /submit_module_for_deliverables_generation -> takes in the course_id, module_id and the reviewed files and submits them for final generation to the deliverables_generation_queue
@router.post("/submit_module_for_deliverables_generation")
async def submit_module_for_deliverables_generation_api(course_id: str = Form(...), module_id: str = Form(...), voice_name: str = Form(...), assessment: bool = Form(...), chatbot: bool = Form(...)):
    return await submit_module_for_deliverables_step(course_id, module_id, 10, voice_name, assessment, chatbot, "in_deliverables_generation_queue")

# /submit_for_publishing_pipeline -> takes in the course_id and submits the course for the publishing pipeline
@router.post("/submit_for_publishing_pipeline")
async def submit_for_publishing_pipeline_api(course_id: str = Form(...), module_id: str = Form(...)):
    return await submit_module_for_step(course_id, module_id, 12, "in_publishing_queue")

@router.post("/submit_for_unpublishing_pipeline")
async def submit_for_unpublishing_pipeline_api(course_id: str = Form(...), module_id: str = Form(...)):
    return await submit_module_for_unpublish(course_id, module_id, 12, "in_publishing_queue")

@router.post("/submit_course_for_publishing_pipeline")
async def submit_for_publishing_pipeline_api(course_id: str = Form(...)):
    return await submit_course_for_publishing(course_id, 13, "in_publishing_queue")

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

@router.post("/add_artifact_to_course")
async def add_artifact_to_course_api(course_id: str = Form(...), 
                                            artifact_type: str = Form(...), 
                                            artifact_id: str = Form(...)):
    return await add_artifact_to_course(course_id, artifact_type, artifact_id)

@router.get("/fetch_quskillbridge_course_id/{course_id}")
async def fetch_qu_skill_bridge_course_id_api(course_id: str):
    return await fetch_qu_skill_bridge_course_id(course_id)