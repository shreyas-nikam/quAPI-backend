from app.services.template_design_services import *
from fastapi import APIRouter, UploadFile, File, Form
from typing import List, Optional

router = APIRouter()


# get all templates
@router.get("/templates")
async def templates_api():
    return await get_templates()

# get template outline
@router.get("/template_outline")
async def template_outline_api(template_id: str = Form(...)):
    return await get_template_outline(template_id)

# save template data
@router.post("/save_template_data")
async def save_template_data_api(template_id: str = Form(...), template_data: list = Form(...)):
    return await save_template_data(template_id, template_data)

# get template reports
@router.get("/template_reports")
async def template_reports_api(template_id: str = Form(...)):
    return await get_template_reports(template_id)

# delete report
@router.post("/delete_report")
async def delete_report_api(template_id: str = Form(...), report_id: str = Form(...)):
    return await delete_report(template_id, report_id)