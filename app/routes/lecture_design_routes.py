from app.services.lecture_design_services import *
from fastapi import APIRouter, UploadFile, File, Form
from typing import List, Optional

router = APIRouter()

# done
@router.post("/generate_lecture_outline")
async def generate_lecture_outline_api(files: Optional[List[UploadFile]] = File(None),
                                  instructions: str = Form(...)):
    return await generate_lecture_outline(files, instructions) 

# /clone_course -> takes in the course_id, course_name, course_image, course_description, and clones the course
@router.post("/clone_lecture")
async def clone_lecture_api(lecture_id: str = Form(...)):
    return await clone_lecture(lecture_id)

# done
@router.post("/delete_lecture")
async def delete_lecture_api(lecture_id: str = Form(...)):
    return await delete_lecture(lecture_id)

# done
@router.post("/create_lecture")
async def create_lecture_api(lecture_name: str = Form(...),  lecture_description: str = Form(...), lecture_outline: str = Form(...), files: Optional[List[UploadFile]] = File(None), lecture_image: UploadFile = File(...)):
    return await create_lecture(lecture_name, lecture_description, lecture_outline, files, lecture_image)

# done
@router.get("/lectures")
async def lectures_api():
    return await get_lectures()

# done
@router.post("/add_resources_to_lecture")
async def add_resources_to_lecture_api(lecture_id: str = Form(...), 
                                      resource_type: str = Form(...), 
                                      resource_name: str = Form(...), 
                                      resource_description: str = Form(...), 
                                      resource_file: Optional[UploadFile] = File(None) ):
    return await add_resources_to_lecture(lecture_id, resource_type, resource_name, resource_description, resource_file)

# done
@router.post("/replace_resources_in_lecture")
async def replace_resources_in_lecture_api(lecture_id: str = Form(...), 
                                          resource_id: str = Form(...), 
                                          resource_type: str = Form(...), 
                                          resource_name: str = Form(...), 
                                          resource_description: str = Form(...), 
                                          resource_file: Optional[UploadFile] = File(None),
                                          lecture_design_step: Optional[int] = Form(None)):
    return await replace_resources_in_lecture(lecture_id=lecture_id, 
                                             resource_id=resource_id, 
                                             resource_type=resource_type, 
                                             resource_name=resource_name, 
                                             resource_description=resource_description, 
                                             resource_file=resource_file if resource_file else None, 
                                             lecture_design_step=lecture_design_step if lecture_design_step else 0)

# done - yet to test with frontend
@router.post("/delete_resources_from_lecture")
async def delete_resources_from_lecture_api(lecture_id: str = Form(...), resource_id: str = Form(...)):
    return await delete_resources_from_lecture(lecture_id, resource_id)

# done
@router.get("/get_lecture/{lecture_id}")
async def get_lecture_api(lecture_id: str):
    return await get_lecture(lecture_id)

# done
@router.post("/submit_lecture_for_content_generation")
async def submit_lecture_for_content_generation_api(lecture_id: str = Form(...), instructions: str = Form(...)):
    return await submit_lecture_for_step(lecture_id, 1, "in_content_generation_queue", instructions)

# done
@router.post("/submit_lecture_for_structure_generation")
async def submit_lecture_for_structure_generation_api(lecture_id: str = Form(...)):
    return await submit_lecture_for_step(lecture_id, 4, "in_structure_generation_queue")

# done
@router.post("/submit_lecture_for_deliverables_generation")
async def submit_lecture_for_deliverables_generation_api(lecture_id: str = Form(...)):
    return await submit_lecture_for_step(lecture_id, 7, "in_deliverables_generation_queue")

# done
@router.post("/submit_for_publishing_pipeline")
async def submit_for_publishing_pipeline_api(lecture_id: str = Form(...)):
    return await submit_lecture_for_step(lecture_id, 9, "in_publishing_queue")

# done
@router.post("/fetch_note")
async def fetch_note_api(url: str = Form(...)):
    return await fetch_note(url)

# done
@router.post("/fetch_quizdata")
async def fetch_quizdata_api(url: str = Form(...)):
    return await fetch_quizdata(url)