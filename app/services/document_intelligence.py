# pip install azure-ai-documentintelligence
import re
import pandas as pd
import os
import logging
from azure.ai.documentintelligence import DocumentIntelligenceClient # type: ignore
from azure.core.credentials import AzureKeyCredential # type: ignore
from azure.ai.documentintelligence.models import ContentFormat # type: ignore 
from PIL import Image
import fitz  # PyMuPDF
import mimetypes
import shutil
import tempfile
from utils.s3_file_manager import S3FileManager
from dotenv import dotenv_values

class Document_intelligence:
    
    def __init__(self):
        self.s3filemanager = S3FileManager()
        env_config  = dotenv_values(".env")
        self.endpoint = env_config["DOCUMENT_INTELLIGENCE_ENDPOINT"]
        self.key = env_config["DOCUMENT_INTELLIGENCE_KEY"]

    def get_field_bounding_regions(self, result):
        res = []

        fields = result.documents[0].fields
        for i in fields:
            if i == "Parties":
                for j, obj in enumerate(fields[i].value):
                    for party_obj in (obj.value):
                        res += obj.value[party_obj].bounding_regions
            else:
                res += fields[i].bounding_regions
        return res

    def get_para_bounding_regions(self, result):
        res = []
        list_of_para = result.paragraphs
        for para in list_of_para:
            temp_dict = para.bounding_regions
            res += temp_dict
        return res

    def get_fields(self, result):
        df_column_names = ["Fields", "Value"]
        df_row = []

        try:
            fields = result.documents[0].fields
            for i in fields:
                if i == "Parties":
                    for j, obj in enumerate(fields[i].value):
                        for party_obj in (obj.value):
                            df_row.append(
                                [f"Party {j+1} : {party_obj}", obj.value[party_obj].content])
                else:
                    df_row.append([i, fields[i].content])

            df = pd.DataFrame(df_row, columns=df_column_names)
            return df
        except:
            df = pd.DataFrame(columns=df_column_names)
            return df
        
    def crop_image_from_image(self, image_path, page_number, bounding_box):
        """
        Crops an image based on a bounding box.

        :param image_path: Path to the image file.
        :param page_number: The page number of the image to crop (for TIFF format).
        :param bounding_box: A tuple of (left, upper, right, lower) coordinates for the bounding box.
        :return: A cropped image.
        :rtype: PIL.Image.Image
        """
        with Image.open(image_path) as img:
            if img.format == "TIFF":
                # Open the TIFF image
                img.seek(page_number)
                img = img.copy()

            # The bounding box is expected to be in the format (left, upper, right, lower).
            cropped_image = img.crop(bounding_box)
            return cropped_image

    def crop_image_from_pdf_page(self, pdf_path, page_number, bounding_box):
        """
        Crops a region from a given page in a PDF and returns it as an image.

        :param pdf_path: Path to the PDF file.
        :param page_number: The page number to crop from (0-indexed).
        :param bounding_box: A tuple of (x0, y0, x1, y1) coordinates for the bounding box.
        :return: A PIL Image of the cropped area.
        """
        doc = fitz.open(pdf_path)
        page = doc.load_page(page_number)

        # Cropping the page. The rect requires the coordinates in the format (x0, y0, x1, y1).
        bbx = [x * 72 for x in bounding_box]
        rect = fitz.Rect(bbx)
        pix = page.get_pixmap(matrix=fitz.Matrix(300/72, 300/72), clip=rect)

        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        doc.close()

        return img

    def crop_image_from_file(self, file_path, page_number, bounding_box):
        """
        Crop an image from a file.

        Args:
            file_path (str): The path to the file.
            page_number (int): The page number (for PDF and TIFF files, 0-indexed).
            bounding_box (tuple): The bounding box coordinates in the format (x0, y0, x1, y1).

        Returns:
            A PIL Image of the cropped area.
        """
        mime_type = mimetypes.guess_type(file_path)[0]

        if mime_type == "application/pdf":
            return self.crop_image_from_pdf_page(file_path, page_number, bounding_box)
        else:
            return self.crop_image_from_image(file_path, page_number, bounding_box)



    def analyze_layout(self, input_file_path, output_directory, model):
        """
        Analyzes the layout of a document and extracts figures along with their descriptions, then update the markdown output with the new description.

        Args:
            input_file_path (str): The path to the input document file.
            output_directory (str): The path to the output folder where the cropped images will be saved.

        Returns:
            str: The updated Markdown content with figure descriptions.

        """
        
        document_intelligence_client = DocumentIntelligenceClient(
            endpoint=self.endpoint, credential=AzureKeyCredential(self.key)
        )
        logging.warning(f"model : {model}")
        with open(input_file_path, "rb") as f:
            poller = document_intelligence_client.begin_analyze_document(
                model_id= "prebuilt-layout", analyze_request=f, content_type="application/octet-stream", output_content_format=ContentFormat.MARKDOWN
            )

        result = poller.result()
        md_content = result.content
        image_output_directory = f"{output_directory}/images"

        if result.figures:
            for idx, figure in enumerate(result.figures):
                figure_content = ""
                img_description = ""
                for i, span in enumerate(figure.spans):
                    figure_content += md_content[span.offset:span.offset + span.length]

                # Note: figure bounding regions currently contain both the bounding region of figure caption and figure body
                try:
                    if figure.caption:
                        caption_region = figure.caption.bounding_regions
                        
                        for region in figure.bounding_regions:
                            if region not in caption_region:
                                # To learn more about bounding regions, see https://aka.ms/bounding-region
                                boundingbox = (
                                        region.polygon[0],  # x0 (left)
                                        region.polygon[1],  # y0 (top)
                                        region.polygon[4],  # x1 (right)
                                        region.polygon[5]   # y1 (bottom)
                                    )
                                cropped_image = self.crop_image_from_file(input_file_path, region.page_number - 1, boundingbox) # page_number is 1-indexed

                                # Get the base name of the file
                                base_name = os.path.basename(input_file_path)
                                # Remove the file extension
                                file_name_without_extension = os.path.splitext(base_name)[0]

                                output_file = f"image_{idx}.png"
                                
                                
                                cropped_image_filename = os.path.join(image_output_directory, output_file)

                                # cropped_image.save(cropped_image_filename)
                                with tempfile.NamedTemporaryFile(suffix='.png', delete=True) as temp_file:
                                    cropped_image.save(temp_file)
                                    self.s3filemanager.upload_file(
                                        local_file_path=temp_file.name, s3_file_name=cropped_image_filename)
                                    self.s3filemanager.make_object_public(s3_file_name=cropped_image_filename)

                    else:
                        for region in figure.bounding_regions:
                            # To learn more about bounding regions, see https://aka.ms/bounding-region
                            boundingbox = (
                                    region.polygon[0],  # x0 (left)
                                    region.polygon[1],  # y0 (top
                                    region.polygon[4],  # x1 (right)
                                    region.polygon[5]   # y1 (bottom)
                                )

                            cropped_image = self.crop_image_from_file(input_file_path, region.page_number - 1, boundingbox) # page_number is 1-indexed

                        # Get the base name of the file
                            base_name = os.path.basename(input_file_path)
                            # Remove the file extension
                            file_name_without_extension = os.path.splitext(base_name)[0]

                            output_file = f"image_{idx}.png"
                            
                            
                            cropped_image_filename = os.path.join(image_output_directory, output_file)

                            # cropped_image.save(cropped_image_filename)
                            with tempfile.NamedTemporaryFile(suffix='.png', delete=True) as temp_file:
                                cropped_image.save(temp_file)
                                self.s3filemanager.upload_file(
                                    local_file_path=temp_file.name, s3_file_name=cropped_image_filename)
                                self.s3filemanager.make_object_public(s3_file_name=cropped_image_filename)

                except Exception as e:
                    logging.warning(f"Skipped image_{idx} because of error {e}")    

        if model == "prebuilt-contract":
            contract_fields = self.get_fields(result)
            s3_file_output = os.path.join(output_directory, "contract_fields.csv")
            self.s3filemanager.df_to_csv_s3(contract_fields, s3_file_output)
            logging.warning(f"Uploaded {s3_file_output}")
        
        md_content = md_content.replace(':unselected:', '')

        # Replace :selected: with ''
        md_content = md_content.replace(':selected:', '')
        
        md_content = re.sub(r'\\\.', '.', md_content)
        
        return md_content
    
    def create_temp_pdf(self,input_file):
        '''
        Create a temporary PDF file from the uploaded file.
        Args:
            input_file (str): The path to the uploaded file.
        Returns:
            str: The path to the temporary directory containing the PDF file.
        '''
        try:
            # Create a temporary directory
            logging.warning("Creating Temp File")
            temp_dir = tempfile.mkdtemp()
            # Write the contents of the uploaded file to a temporary PDF file
            pdf_name = os.path.basename(input_file)
            temp_pdf_path = os.path.join(temp_dir, pdf_name)
            self.s3filemanager.download_file(input_file, temp_pdf_path)
            logging.warning(f"Temp File Created : {temp_pdf_path}")
            return temp_dir
        except Exception as e:
            logging.error(f"Error occurred while creating temporary PDF: {str(e)}")
            return None 

    def main(self, file, output_directory, model = "prebuilt-layout"):
        '''
        Main function to extract text from the PDF file and save the output to a CSV file.
        Args:
            file (str): The path to the PDF file.
            output_directory (str): The directory where the output CSV file will be saved.
        Returns:
            str: The path to the output CSV file.
        '''
        try:
            # Read input PDF file
            logging.warning(f"Text extraction process started")
            pdf_name = os.path.basename(file)[:-4]
            temp_dir = self.create_temp_pdf(file)
            temp_pdf_path = os.path.join(temp_dir, os.path.basename(file))
            
            md_content = self.analyze_layout(temp_pdf_path, output_directory, model)
            
            mmd_s3_file_name = os.path.join(output_directory, f"output-text.mmd")

            self.s3filemanager.put_object(mmd_s3_file_name, md_content.encode('utf-8'))
            
            return {'status': "success", 'output': mmd_s3_file_name}

        except Exception as e:
            logging.error(f"An error occurred in document intelligence processing: {e}")
            return {'status': "failed", 'output': str(e)}
        
        finally:
            shutil.rmtree(temp_dir)