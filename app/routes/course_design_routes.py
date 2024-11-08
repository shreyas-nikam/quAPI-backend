from app.services.course_design_services import get_courses, generate_course_outline, clone_course, delete_course, create_course, add_module, add_resources_to_module, get_course, save_changes_after_step, submit_module_for_step
from fastapi import APIRouter, UploadFile, File, Form
from typing import List

router = APIRouter()

# /generate_course_outline -> take in the input as the file and the instructions and generate the course outline
@router.post("/generate_course_outline")
async def generate_course_outline_api(files: List[UploadFile] = File(...),
                                  instructions: str = Form(...)):
    return await generate_course_outline(files, instructions) 

# /clone_course -> takes in the course_id, course_name, course_image, course_description, and clones the course
@router.post("/clone_course")
async def clone_course_api(payload: dict):
    return await clone_course(payload)

# /delete_course -> takes in the course_id and deletes the course
@router.post("/delete_course")
async def delete_course_api(payload: dict):
    return await delete_course(payload)

# /create_course -> takes in the course name, course image, course description, files, course_outline, and creates a course object. also handles creation of modules
@router.post("/create_course")
async def create_course_api(course_name: str, course_image: UploadFile = File(...), course_description: str = Form(...), course_outline: str = Form(...), files: List[UploadFile] = File(...)):
    return await create_course(course_name, course_image, course_description, course_outline, files)

# /courses -> returns all the courses
@router.get("/courses")
async def courses_api():
    return await get_courses()


# /add_module -> takes in the course_id, module_name, module_description, and adds a module to the course
@router.post("/add_module")
async def add_module_api(payload: dict):
    return await add_module(payload)

# /add_resources_to_module -> takes in the course_id, module_id, resource_type, resource_name, resource_description, resource_link, and adds a resource to the module and to s3
@router.post("/add_resources_to_module")
async def add_resources_to_module_api(payload: dict):
    return await add_resources_to_module(payload)

# /replace_resources_in_module -> takes in the course_id, module_id, resource_id, resource_type, resource_name, resource_description, resource_link, and replaces the resource in the module and s3
@router.post("/replace_resources_in_module")
async def replace_resources_in_module_api(payload: dict):
    pass

# /delete_resources_from_module -> takes in the course_id, module_id, resource_id, and deletes the resource from the module and s3
@router.post("/delete_resources_from_module")
async def delete_resources_from_module_api(payload: dict):
    pass

# /get_course -> takes in the course_id and returns the course object
@router.get("/get_course")
async def get_course_api(course_id: int):
    return await get_course(course_id)

# /submit_module_for_content_generation -> takes in the course_id, module_id, and submits the module for content generation to the content_generation_queue
@router.post("/submit_module_for_content_generation")
async def submit_module_for_content_generation_api(payload: dict):
    return await submit_module_for_step(payload, 1, "in_content_generation_queue")

# /save_changes_post_content_generation -> takes in the course_id, module_id, reviewed files, and saves the changes to the module
@router.post("/save_changes_post_content_generation")
async def save_changes_post_content_generation_api(payload: dict):
    return await save_changes_after_step(payload, 3)

# /submit_module_for_structure_generation -> takes in the course_id, module_id and the reviewed files and submits them for structure generation to the structure_generation_queue
@router.post("/submit_module_for_structure_generation")
async def submit_module_for_structure_generation_api(payload: dict):
    return await submit_module_for_step(payload, 4, "in_structure_generation_queue")

# /save_changes_post_structure_generation -> takes in the course_id, module_id, reviewed files, and saves the changes to the module
@router.post("/save_changes_post_structure_generation")
async def save_changes_post_structure_generation_api(payload: dict):
    return await save_changes_after_step(payload, 6)

# /submit_module_for_deliverables_generation -> takes in the course_id, module_id and the reviewed files and submits them for final generation to the deliverables_generation_queue
@router.post("/submit_module_for_deliverables_generation")
async def submit_module_for_deliverables_generation_api(payload: dict):
    return await submit_module_for_step(payload, 7, "in_deliverables_generation_queue")

# /save_changes_post_deliverables_generation -> takes in the course_id, module_id, reviewed files, and saves the changes to the module
@router.post("/save_changes_post_deliverables_generation")
async def save_changes_post_deliverables_generation_api(payload: dict):
    return await save_changes_after_step(payload, 8)

# /submit_for_publishing_pipeline -> takes in the course_id and submits the course for the publishing pipeline
@router.post("/submit_for_publishing_pipeline")
async def submit_for_publishing_pipeline_api(payload: dict):
    return await submit_module_for_step(payload, 9, "in_publishing_queue")