# External imports
from pathlib import Path
import os
import boto3
import tempfile
from botocore.exceptions import NoCredentialsError, ClientError
import logging
import tempfile
from dotenv import load_dotenv
import os

# Load the environment variables
load_dotenv()


class S3FileManager:
    """
    A class to interact with AWS S3.

    Attributes:
    -----------
    aws_access_key_id: str
        The AWS access key ID.
    aws_secret_access_key: str
        The AWS secret access key.
    bucket_name: str
        The name of the bucket.
    s3_client: S3 client
        The S3 client.


    Methods:
    --------
    upload_file(file_path, key)
        Upload a file to S3.
    upload_temp_file(file, key)
        Upload a temporary file to S3.
    list_files(key)
        List all files in the S3 bucket with the given key.
    download_file(key, download_path)
        Download a file from S3.
    delete_file(key)
        Delete a file from S3.
    upload_file_from_bytes(data, key)
        Upload a file to S3 from bytes.
    download_file_to_bytes(key)
        Download a file from S3 to bytes.
    get_object(key)
        Get an object from S3.

    """

    def __init__(self):
        """
        Constructor for the S3FileManager class.
        """

        # Initialize AWS credentials and S3 client
        self.aws_access_key_id = os.environ.get("AWS_ACCESS_KEY")
        self.aws_secret_access_key = os.environ.get("AWS_SECRET_KEY")
        self.bucket_name = os.environ.get("AWS_BUCKET_NAME")
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

    def upload_file_obj(self, file_obj, key):
        """
        Upload a file object to S3

        Args:
        file_obj: file object - file object to be uploaded
        key: str - key to be used in the S3 bucket

        Returns:
        bool: True if the file was uploaded successfully, False otherwise
        """
        try:
            self.s3_client.upload_fileobj(file_obj, self.bucket_name, key)
            self.make_object_public(key)
            return True
        except FileNotFoundError:
            logging.error("The file was not found")
            return False
        except NoCredentialsError:
            logging.error("Credentials not available")
            return False
        except ClientError as e:
            logging.error(e)
            return False

    def upload_file(self, file_path, key):
        """
        Upload a file to S3

        Args:
        file_path: str - path to the file to be uploaded
        key: str - key to be used in the S3 bucket

        Returns:
        bool: True if the file was uploaded successfully, False otherwise
        """
        try:
            self.s3_client.upload_file(file_path, self.bucket_name, key)
            self.make_object_public(key)
            return True
        except FileNotFoundError:
            logging.error("The file was not found")
            return False
        except NoCredentialsError:
            logging.error("Credentials not available")
            return False
        except ClientError as e:
            logging.error(e)
            return False

    def upload_temp_file(self, file, key):
        """
        Upload a temporary file to S3

        Args:
        file: bytes - file data to be uploaded
        key: str - key to be used in the S3 bucket

        Returns:
        bool: True if the file was uploaded successfully, False otherwise
        """
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(file)
                temp_file.close()
                self.upload_file(temp_file.name, key)
                os.unlink(temp_file.name)
            return True
        except NoCredentialsError:
            logging.error("Credentials not available")
            return False
        except ClientError as e:
            logging.error(e)
            return False
        
    def make_object_public(self, s3_file_name):
        s3_file_name = str(Path(s3_file_name).as_posix())
        try:
            self.s3_client.put_object_acl(
                ACL='public-read', Bucket=self.bucket_name, Key=s3_file_name)
            logging.info(
                f"Object '{s3_file_name}' made public in S3 bucket '{self.bucket_name}'")
            return True
        except NoCredentialsError:
            logging.error("AWS credentials not available or incorrect.")
            print("AWS credentials not available or incorrect.")
            return False
        except Exception as e:
            logging.error(f"An error occurred: make_object_public: {e}")
            print(f"An error occurred: make_object_public: {e}")
            return False
        
    def copy_file(self, source_key, destination_key):
        """
        Copy a file in S3

        Args:
        source_key: str - key of the source file in the S3 bucket
        destination_key: str - key of the destination file in the S3 bucket

        Returns:
        bool: True if the file was copied successfully, False otherwise
        """
        try:
            self.s3_client.copy_object(
                Bucket=self.bucket_name, CopySource=f"{self.bucket_name}/{source_key}", Key=destination_key)
            return True
        except NoCredentialsError:
            logging.error("Credentials not available")
            return False
        except ClientError as e:
            logging.error(e)
            return False

    def list_files(self, key):
        """
        List all files in the S3 bucket with the given key

        Args:
        key: str - key of the files in the S3 bucket

        Returns:
        list: List of files in the S3 bucket with the given key
        """
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name, Prefix=key)
            return response.get("Contents")
        except NoCredentialsError:
            logging.error("Credentials not available")
            return False
        except ClientError as e:
            logging.error(e)
            return False

    def download_file(self, key, download_path):
        """
        Download a file from S3

        Args:
        key: str - key of the file in the S3 bucket
        download_path: str - path to download the file

        Returns:
        bool: True if the file was downloaded successfully, False otherwise
        """
        try:
            with open(download_path, 'wb') as f:
                self.s3_client.download_fileobj(self.bucket_name, key, f)
            return True
        except NoCredentialsError:
            logging.error("Credentials not available")
            return False
        except ClientError as e:
            logging.error(e)
            return False

    def delete_file(self, key):
        """
        Delete a file from S3

        Args:
        key: str - key of the file in the S3 bucket

        Returns:
        bool: True if the file was deleted successfully, False otherwise
        """
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=key)
            return True
        except NoCredentialsError:
            logging.error("Credentials not available")
            return False
        except ClientError as e:
            logging.error(e)
            return False

    def upload_file_from_bytes(self, data, key):
        """
        Upload a file to S3 from bytes

        Args:
        data: bytes - data to be uploaded
        key: str - key to be used in the S3 bucket

        Returns:
        bool: True if the file was uploaded successfully, False otherwise
        """
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(data)
                temp_file.close()
                self.upload_file(temp_file.name, key)
                os.unlink(temp_file.name)
            return True
        except NoCredentialsError:
            logging.error("Credentials not available")
            return False
        except ClientError as e:
            logging.error(e)
            return False

    def download_file_to_bytes(self, key):
        """
        Download a file from S3 to bytes

        Args:
        key: str - key of the file in the S3 bucket

        Returns:
        bytes: data of the file
        """
        try:
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.close()
                self.download_file(key, temp_file.name)
                with open(temp_file.name, 'rb') as f:
                    data = f.read()
                os.unlink(temp_file.name)
            return data
        except NoCredentialsError:
            logging.error("Credentials not available")
            return False
        except ClientError as e:
            logging.error(e)
            return False

    def get_object(self, key):
        """
        Get an object from S3

        Args:
        key: str - key of the object in the S3 bucket

        Returns:
        bytes: data of the object
        """
        try:
            response = self.s3_client.get_object(
                Bucket=self.bucket_name, Key=key)
            content = response['Body'].read()
            return content
        except NoCredentialsError:
            logging.error("Credentials not available")
            return False
        except ClientError as e:
            logging.error(e)
            return False

    def upload_directory(self, directory_path, key):
        """
        Upload a directory to S3

        Args:
        directory_path: str - path to the directory to be uploaded
        key: str - key to be used in the S3 bucket

        Returns:
        bool: True if the directory was uploaded successfully, False otherwise
        """
        try:
            for root, dirs, files in os.walk(directory_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    s3_key = key + file_path[len(directory_path):]
                    self.upload_file(file_path, s3_key)
            return True
        except NoCredentialsError:
            logging.error("Credentials not available")
            return False
        except ClientError as e:
            logging.error(e)
            return False
        

    def download_directory(self, key, download_path):
        """
        Download a directory from S3

        Args:
        key: str - key of the directory in the S3 bucket
        download_path: str - path to download the directory

        Returns:
        bool: True if the directory was downloaded successfully, False otherwise
        """
        try:
            for obj in self.list_files(key):
                file_key = obj['Key']
                file_path = os.path.join(download_path, file_key[len(key):])
                self.download_file(file_key, file_path)
            return True
        except NoCredentialsError:
            logging.error("Credentials not available")
            return False
        except ClientError as e:
            logging.error(e)
            return False
        
    