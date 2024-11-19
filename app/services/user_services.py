from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from app.utils.atlas_client import AtlasClient
from pydantic import EmailStr
from datetime import datetime

# List of valid project types
Project_Options = [
    "courses", "research_report", "create_a_video", "white_paper",
    "project_plan", "e_book", "create_a_podcast", "write_a_blog",
]

# Email validation using Pydantic (or you can use regex here as well)
def validate_email(email: str) -> bool:
    try:
        EmailStr.validate(email)
        return True
    except ValueError:
        return False

# Date validation (assuming date format is 'YYYY-MM-DD')
def validate_date(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")  # Check if date matches 'YYYY-MM-DD'
        return True
    except ValueError:
        return False

async def add_user_to_project_waitlist(user_id, user_email, project_id, project_name, date):
    print(f"Received Parameters: user_id={user_id}, user_email={user_email}, project_id={project_id}, project_name={project_name}, date={date}")
    
    print("In add_user_to_project_waitlist")
    atlas_client = AtlasClient()

    # Validate email format
    # if not validate_email(user_email):
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format.")
    
    # Validate date format
    if not validate_date(date):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format. Expected 'YYYY-MM-DD'.")
    
    # Ensure the project exists in the allowed project options
    if project_id not in Project_Options:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid project name. Valid options are: {', '.join(Project_Options)}"
        )
    
    # Check if the user has already signed up for the waitlist for the project
    user_project = atlas_client.find("project_waitlist", filter={"user_id": user_id, "project_id": project_id})
    
    if user_project:
        # If the user is already in the waitlist for this project, return a message
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"message": "User is already on the waitlist for this project."}
        )
    
    # If not, add the user to the waitlist
    waitlist_entry = {
        "user_id": user_id,
        "user_email": user_email,
        "project_id": project_id,
        "project_name": project_name,
        "date": date,  # Date should already be validated
    }
    
    # Insert the new entry into the database
    try:
        atlas_client.insert("project_waitlist", waitlist_entry)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to insert waitlist entry: {str(e)}"
        )
    
    # Return a success response
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "User successfully added to the waitlist."}
    )
    print(f"Received Parameters: user_id={user_id}, user_email={user_email}, project_id={project_id}, project_name={project_name}, date={date}")
    
    print("In add_user_to_project_waitlist")
    atlas_client = AtlasClient()
    # Validate email format
    # if not validate_email(user_email):
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email format.")
    
    # Validate date format
    if not validate_date(date):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format. Expected 'YYYY-MM-DD'.")
    
    # Ensure the project exists in the COURSE_DESIGN_STEPS
    if project_id not in Project_Options:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid project name. Valid options are: {', '.join(Project_Options)}")
    
    # Check if the user has already signed up for the waitlist for the project
    user_project = atlas_client.find("project_waitlist",  filter={"user_id": user_id, "project_id": project_id}  )
    
    if user_project:
        # If the user is already in the waitlist for this project, return a message
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"message": "User is already on the waitlist for this project."}
        )
    
    # If not, add the user to the waitlist
    waitlist_entry = {
        "user_id": user_id,
        "user_email": user_email,
        "project_id": project_id,
        "project_name": project_name,
        "date": date,  # Date should already be validated
    }
    
    # Insert the new entry into the database
    atlas_client.find("project_waitlist").insert(waitlist_entry)
    
    # Return a success response
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "User successfully added to the waitlist."}
    )