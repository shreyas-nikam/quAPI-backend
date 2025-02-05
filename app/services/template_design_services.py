# Import necessary modules and packages
from pathlib import Path
from app.utils.s3_file_manager import S3FileManager
from app.utils.atlas_client import AtlasClient
import ast
from bson.objectid import ObjectId
import os
from app.services.qu_audit.qu_audit import *
import fitz


def _convert_object_ids_to_strings(data):
    if isinstance(data, dict):
        return {key: _convert_object_ids_to_strings(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [_convert_object_ids_to_strings(item) for item in data]
    elif isinstance(data, ObjectId):
        return str(data)
    else:
        return data
    

# Function to get all templates
async def get_templates():
    """
    Get all templates
    
    Returns:
    - list of templates
    """
    mongo_client = AtlasClient()  # Initialize MongoDB client

    templates = mongo_client.find("model_templates", {})  # Find all templates

    redacted_templates = []
    
    # Redact template details
    for template in templates:
        redacted_templates.append({
            "_id": str(template["_id"]),
            "name": template["name"],
            "note": template["note"],
        })

    return _convert_object_ids_to_strings(redacted_templates)  # Return redacted templates

# Function to get template details
async def get_template_details(template_id):
    """
    Get template outline
    
    Args:
    - template_id: str
    
    Returns:
    - template outline
    """
    mongo_client = AtlasClient()  # Initialize MongoDB client

    template_details  = mongo_client.find("model_templates", {"_id": ObjectId(template_id)})  # Find template by ID

    return _convert_object_ids_to_strings(template_details)  # Return template details

# Function to convert table data to string
def convert_table_data_to_string(table_data):
    """
    Convert table data to string

    Input table data: [{"name": "John", "age": 25}, {"name": "Jane", "age": 30}]
    Output string: <table><tr><th>name</th><th>age</th></tr><tr><td>John</td><td>25</td></tr><tr><td>Jane</td><td>30</td></tr></table>
    
    Args:
    - table_data: dict
    
    Returns:
    - str
    """
    table = "<table>"
    table += "<tr>"
    for key in table_data[0].keys():
        table += f"<th>{key}</th>"
    table += "</tr>"
    for row in table_data:
        table += "<tr>"
        for key in row.keys():
            table += f"<td>{row[key]}</td>"
        table += "</tr>"
    table += "</table>"
    return table  # Return table as string

# Function to save template data
async def save_template_data(template_id, template_data):
    """
    Save template data

    Args:
    - template_id: str
    - template_data: list of dicts of keys name, value, and type

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

    mongo_client = AtlasClient()  # Initialize MongoDB client

    # Get template name
    template_name = mongo_client.find("model_templates", {"_id": ObjectId(template_id)})[0]["name"]

    report_inputs = TemplateValue({})  # Initialize template values
    tables = []  # List to store table data

    # Process template data
    for key in template_data.keys():
        if type(template_data[key]) == list:
            # Convert table data to string and add to tables list
            tables.append(Note(category='embed', title=key, value=convert_table_data_to_string(ast.literal_eval(template_data[key]))))
        else:
            # Set value for non-table data
            report_inputs.set_value(key, template_data[key])

    # Initialize report generator
    report_generator = ReportGenerator(name=template_name, version="1.0", category="basic")
    for table in tables:
        # Add table notes to report generator
        report_generator.add_note(table)

    report_generator.load(report_inputs)  # Load template values into report generator

    report_generator.generate()  # Generate the report

    report_generator.get_html()  # Get the generated HTML

    report_id = ObjectId()  # Generate a new ObjectId for the report

    # Save the generated HTML report locally
    report_generator.save_html(f"reports/{report_id}.html")

    s3_file_manager = S3FileManager()  # Initialize S3 file manager
    
    s3_key = f"qu-model-design/reports/{report_id}.html"  # Define S3 key for the report
    await s3_file_manager.upload_file(f"reports/{report_id}.html", s3_key)  # Upload report to S3

    s3_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{s3_key}"  # Generate S3 link for the report

    os.remove(f"reports/{report_id}.html")  # Remove local HTML file

    mongo_client.insert("model_reports", {"_id": report_id, "template_id": template_id, "name": template_name, "url": s3_link, "original_data": template_data})  # Insert report details into MongoDB

    # Return report details
    report_data = mongo_client.find("model_reports", {"_id": report_id})[0]

    return _convert_object_ids_to_strings(report_data)  # Return report details

# Function to delete a report
async def delete_report(project_id, template_id, report_id):
    mongo_client = AtlasClient()
    project = mongo_client.find("model_projects", {"_id": ObjectId(project_id)})
    if not project:
        return "Project not found"
    project = project[0]

    for index, template in enumerate(project["templates"]):
        if template["template_id"] == template_id:
            project["templates"][index]["report_ids"].remove(report_id)
            break

    mongo_client.update("model_projects", {"_id": ObjectId(project_id)}, {"$set": {"templates": project[0]["templates"]}})
    mongo_client.delete("model_reports", {"_id": ObjectId(report_id)})

    return True

# Function to create a model project
async def create_model_project(project_name, project_description):
    mongo_client = AtlasClient()
    project_id = mongo_client.insert("model_projects", {"name": project_name, "description": project_description})
    return _convert_object_ids_to_strings({"_id": str(project_id), "name": project_name, "description": project_description})

# Function to get all model projects
async def get_model_projects():
    mongo_client = AtlasClient()
    projects = mongo_client.find("model_projects", {})
    redacted_projects = []
    for project in projects:
        redacted_projects.append({
            "_id": str(project["_id"]),
            "name": project["name"],
            "description": project["description"],
        })
    return _convert_object_ids_to_strings(redacted_projects)

# Function to get a model project
async def get_model_project(project_id):
    mongo_client = AtlasClient()
    project = mongo_client.find("model_projects", {"_id": ObjectId(project_id)})
    templates = []
    for template in project[0]["templates"]:
        template_id = template["template_id"]
        template_details = mongo_client.find("model_templates", {"_id": ObjectId(template_id)})
        redacted_template = {
            "_id": str(template_details[0]["_id"]),
            "name": template_details[0]["name"],
            "note": template_details[0]["note"],
        }
        templates.append(redacted_template)
    
    project[0]["templates"] = templates
    
    if project:
        return _convert_object_ids_to_strings(project[0])
    else:
        return "Project not found"

# Function to delete a model project
async def delete_model_project(project_id):
    mongo_client = AtlasClient()
    project = mongo_client.find("model_projects", {"_id": ObjectId(project_id)})
    if project:
        mongo_client.delete("model_projects", {"_id": ObjectId(project_id)})
        return True
    else:
        return "Project not found"

# Function to import templates to a project
async def import_templates_to_project(project_id, template_ids):
    mongo_client = AtlasClient()
    project = mongo_client.find("model_projects", {"_id": ObjectId(project_id)})
    templates = []
    if project:
        for template_id in template_ids:
            templates.append({"template_id": str(template_id), "report_ids": [], "status": "pending"})
        
        mongo_client.update("model_projects", {"_id": ObjectId(project_id)}, {"$set": {"templates": templates}})
        return get_model_project(project_id)
    else:
        return "Project not found"

# Function to get the reports for a template in a project
async def get_project_template_reports(project_id, template_id):
    mongo_client = AtlasClient()
    project = mongo_client.find("model_projects", {"_id": ObjectId(project_id)})
    template_reports = []
    if project:
        for template in project[0]["templates"]:
            if template["template_id"] == template_id:
                for report_id in template["report_ids"]:
                    report = mongo_client.find("model_reports", {"_id": ObjectId(report_id)})
                    template_reports.append(report[0])
        return _convert_object_ids_to_strings(template_reports)
    else:
        return "Project not found"

# Function to save project template data
async def save_project_template_data(project_id, template_id, template_data):
    mongo_client = AtlasClient()
    project = mongo_client.find("model_projects", {"_id": ObjectId(project_id)})
    if not project:
        return "Project not found"
    project = project[0]

    report_id = save_template_data(template_id, template_data)
    
    report_ids = []
    for index, template in enumerate(project["templates"]):
        if template["template_id"] == template_id:
            project["templates"][index]["report_ids"].append(report_id)
            project["templates"][index]["status"] = "completed"
            report_ids = project["templates"][index]["report_ids"]
            break

    report_datas = []
    for report_id in report_ids:
        report = mongo_client.find("model_reports", {"_id": ObjectId(report_id)})
        report_data = {
            "report_id": str(report_id),
            "name": report[0]["name"],
            "url": report[0]["url"]
        }
        report_datas.append(report_data)

    mongo_client.update("model_projects", {"_id": ObjectId(project_id)}, {"$set": {"templates": project["templates"]}})
    return _convert_object_ids_to_strings(report_datas)

# Function to get sample data for a template
async def get_sample_data(template_id):
    mongo_client = AtlasClient()
    template = mongo_client.find("model_templates", {"_id": ObjectId(template_id)})
    return _convert_object_ids_to_strings(template[0]["sample_data"])

# Function to get sample report for a template
async def get_sample_report(template_id):
    mongo_client = AtlasClient()
    template = mongo_client.find("model_templates", {"_id": ObjectId(template_id)})
    return _convert_object_ids_to_strings(template[0]["sample_report"])

# Function to combine pdfs
def combine_pdfs(pdf_urls):
    # Steps:
    # 1. Download all the pdfs from the urls
    # 2. Combine the pdfs into a single pdf
    # 3. Upload the combined pdf to the s3 bucket
    # 4. Return the url of the combined pdf

    s3_file_manager = S3FileManager()  # Initialize S3 file manager

    pdf_files = []  # List to store pdf files

    # Download all the pdfs from the urls
    unique_id = ObjectId()
    output_path = f"reports/{unique_id}/"  # Define output path for the combined pdf
    Path(output_path).mkdir(parents=True, exist_ok=True)  # Create output directory

    # download all the pdfs
    for index, pdf_url in enumerate(pdf_urls):
        pdf_file = f"{output_path}{index}.pdf"  # Define pdf file path
        pdf_files.append(pdf_file)  # Add pdf file to pdf_files list
        s3_key = pdf_url.split("/")[3] + "/" + "/".join(pdf_url.split("/")[4:])  # Define S3 key for the pdf

        s3_file_manager.download_file(s3_key, pdf_file)  # Download pdf file from S3

    combined_pdf_file = f"reports/{unique_id}/combined.pdf"  # Define path for the combined pdf file

    # Combine the pdfs into a single pdf
    pdf_writer = fitz.open()  # Initialize PDF writer

    for pdf_file in pdf_files:
        pdf_reader = fitz.open(pdf_file)
        pdf_writer.insert_pdf(pdf_reader)
        pdf_reader.close()

    pdf_writer.save(combined_pdf_file)  # Save the combined pdf file

    s3_key = f"qu-model-design/reports/{unique_id}/combined.pdf"  # Define S3 key for the combined pdf
    s3_file_manager.upload_file(combined_pdf_file, s3_key)  # Upload the combined pdf to S3

    s3_link = f"https://qucoursify.s3.us-east-1.amazonaws.com/{s3_key}"  # Generate S3 link for the combined pdf

    for pdf_file in pdf_files:
        os.remove(pdf_file)
    
    os.remove(combined_pdf_file)  # Remove the combined pdf file

    return s3_link  # Return the S3 link for the combined pdf

# Function to consolidate all reports
async def consolidate_reports(project_id):
    mongo_client = AtlasClient()
    project = mongo_client.find("model_projects", {"_id": ObjectId(project_id)})
    if not project:
        return "Project not found"
    project = project[0]

    report_ids = []
    for template in project["templates"]:
        report_ids += template["report_ids"][-1]
    
    # get all the pdf urls for the reports
    pdf_urls = []
    for report_id in report_ids:
        report = mongo_client.find("model_reports", {"_id": ObjectId(report_id)})
        pdf_urls.append(report[0]["url"])
    

    # combine the pdfs into a single pdf
    combined_pdf_url = combine_pdfs(pdf_urls)

    #  insert the url in the model_projects collection
    mongo_client.update("model_projects", {"_id": ObjectId(project_id)}, {"$set": {"consolidated_report": combined_pdf_url}})

    return combined_pdf_url

# Function to get the completion status of a project
async def get_completion_status(project_id):
    mongo_client = AtlasClient()
    project = mongo_client.find("model_projects", {"_id": ObjectId(project_id)})
    if not project:
        return "Project not found"
    project = project[0]

    for template in project["templates"]:
        if len(template["report_ids"])>0:
            continue
        else:
            return False

    return True