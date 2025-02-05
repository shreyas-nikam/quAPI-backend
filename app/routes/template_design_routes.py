from app.services.template_design_services import get_templates, get_template_details, delete_report, create_model_project, get_model_projects, get_model_project, delete_model_project, import_templates_to_project, get_project_template_reports, save_project_template_data, get_sample_data, get_sample_report, consolidate_reports, get_completion_status
from fastapi import APIRouter, UploadFile, File, Form
from typing import List, Optional

router = APIRouter()


# get all templates
@router.get("/templates")
async def templates_api():
    return await get_templates()

# get template outline
@router.post("/template_details")
async def template_details_api(template_id: str = Form(...)):
    return await get_template_details(template_id)

# get sample data for template
@router.post("/sample_data")
async def sample_data_api(template_id: str = Form(...)):
    return await get_sample_data(template_id)

# get sample report for template
@router.post("/sample_report")
async def sample_report_api(template_id: str = Form(...)):
    return await get_sample_report(template_id)

# create model project
@router.post("/create_model_project")
async def create_model_project_api(project_name: str = Form(...), project_description: str = Form(...)):
    return await create_model_project(project_name, project_description)

# get model projects
@router.get("/model_projects")
async def model_projects_api():
    return await get_model_projects()

# get model project from id
@router.post("/model_project")
async def model_project_api(project_id: str = Form(...)):
    return await get_model_project(project_id)

# delete report
@router.post("/delete_report")
async def delete_report_api(project_id: str = Form(...), template_id: str = Form(...), report_id: str = Form(...)):
    return await delete_report(project_id, template_id, report_id)

# delete model project
@router.post("/delete_model_project")
async def delete_model_project_api(project_id: str = Form(...)):
    return await delete_model_project(project_id)

# import templates to project
@router.post("/import_templates_to_project")
async def import_templates_to_project_api(project_id: str = Form(...), template_ids: list = Form(...)):
    return await import_templates_to_project(project_id, template_ids)

# save project template data
@router.post("/save_project_template_data")
async def save_project_template_data_api(project_id: str = Form(...), template_id: str = Form(...), template_data: list = Form(...)):
    return await save_project_template_data(project_id, template_id, template_data)

# consolidate all reports
@router.post("/consolidate_reports")
async def consolidate_reports_api(project_id: str = Form(...)):
    return await consolidate_reports(project_id)

# get status of completion
@router.post("/get_completion_status")
async def get_completion_status_api(project_id: str = Form(...)):
    return await get_completion_status(project_id)
