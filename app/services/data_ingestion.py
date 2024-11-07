
import os
import logging
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.services.document_intelligence import Document_intelligence



class PDFRequest(BaseModel):
    s3_pdf_path: str
    s3_root_directory: str
    model : Optional[str] = None
    job_id : Optional[str] = None


@app.post("/azure_document_intelligence/")
async def azure_document_intelligence(pdf_request: PDFRequest):
    """
    Parse a PDF file located in an S3 bucket and save the output CSV file to a specified directory using Azure Document Intelligence.

    Args:
        s3_pdf_path (str): The S3 path to the PDF file.
        s3_root_directory (str): The S3 directory where the output CSV file will be saved.
        model 

    Returns:
        dict: A dictionary containing the status of the operation and the S3 path to the output CSV file.
    """
    try:
        logging.warning("Called document intelligence API to extract information")

        document_intelligence = Document_intelligence()
        
        pdf_name = os.path.basename(pdf_request.s3_pdf_path)[:-4]
        output_directory = os.path.join(pdf_request.s3_root_directory,f"{pdf_name}/output_files")
        if pdf_request.model:
            result = document_intelligence.main(pdf_request.s3_pdf_path, output_directory, pdf_request.model)
        else: 
            result = document_intelligence.main(pdf_request.s3_pdf_path, output_directory)
        if result['status'] == "success":
            return PDFResponse(status="success", s3_output_path=result['output'])
        else:
            raise HTTPException(status_code=500, detail=f"Failed to parse PDF. ERROR: {result['output']}")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="PDF file not found.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))