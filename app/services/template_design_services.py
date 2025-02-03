# Import necessary modules and packages
from app.utils.s3_file_manager import S3FileManager
from app.utils.atlas_client import AtlasClient
import ast
from bson.objectid import ObjectId
import os
from app.services.qu_audit.qu_audit import *

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

    return redacted_templates  # Return redacted templates

# Function to get template outline
async def get_template_outline(template_id):
    """
    Get template outline
    
    Args:
    - template_id: str
    
    Returns:
    - template outline
    """
    mongo_client = AtlasClient()  # Initialize MongoDB client

    template_outline  = mongo_client.find("model_templates", {"_id": ObjectId(template_id)})  # Find template by ID

    return template_outline  # Return template outline

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
    for row in template_data:
        if row['type'] == 'table':
            # Convert table data to string and add to tables list
            tables.append(Note(category='embed', title=row['name'], value=convert_table_data_to_string(ast.literal_eval(row['value']))))
        else:
            # Set value for non-table data
            report_inputs.set_value(row['name'], row['value'])

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

    # Return report details
    return {
        "report_id": str(report_id),
        "template_id": template_id,
        "name": template_name,
        "url": s3_link,
    }

# Function to get template reports
async def get_template_reports(template_id):
    """
    Get template reports
    
    Args:
    - template_id: str
    
    Returns:
    - list of template reports
    """
    mongo_client = AtlasClient()  # Initialize MongoDB client

    reports = mongo_client.find("model_reports", {"template_id": template_id})  # Find reports by template ID

    redacted_reports = []
    
    # Redact report details
    for report in reports:
        redacted_reports.append({
            "_id": str(report["_id"]),
            "template_id": report["template_id"],
            "name": report["name"],
            "url": report["url"],
        })

    return redacted_reports  # Return redacted reports

# Function to delete a report
async def delete_report(template_id, report_id):
    """
    Delete report
    
    Args:
    - template_id: str
    - report_id: str
    
    Returns:
    - None
    """
    mongo_client = AtlasClient()  # Initialize MongoDB client

    report = mongo_client.find("model_reports", {"_id": ObjectId(report_id)})  # Find report by ID

    if report:
        mongo_client.delete("model_reports", {"_id": ObjectId(report_id)})  # Delete report
        return "Report deleted"
    else:
        return "Report not found"