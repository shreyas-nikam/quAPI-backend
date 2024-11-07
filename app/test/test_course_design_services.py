from app.services.course_design_services import generate_course_outline, clone_course, delete_course, create_course, add_module, add_resources_to_module, get_course, save_changes_after_step, submit_module_for_step

# write tests for all the above functions

def test_generate_course_outline():
    payload = {
        "course_name": "Test Course",
        "course_image": "test.jpg",
        "course_description": "This is a test course",
        "files": ["test1.pdf"],
        "instructions": "This is the course instructions"
    }
    generate_course_outline(payload)

def test_clone_course():
    payload = {
        "course_id": 1,
        "course_name": "Test Course",
        "course_image": "test.jpg",
        "course_description": "This is a test course"
    }
    assert clone_course(payload) == "Course cloned"

def test_delete_course():
    payload = {
        "course_id": 1
    }
    assert delete_course(payload) == "Course deleted"

def test_create_course():
    payload = {
        "course_name": "Test Course",
        "course_image": "test.jpg",
        "course_description": "This is a test course",
        "files": ["test1.jpg", "test2.jpg"],
        "course_outline": "This is the course outline"
    }
    assert create_course(payload) == "Course created"

def test_add_module():
    payload = {
        "course_id": 1,
        "module_name": "Test Module",
        "module_description": "This is a test module"
    }
    assert add_module(payload) == "Module added"

def test_add_resources_to_module():
    payload = {
        "course_id": 1,
        "module_id": 1,
        "resource_type": "video",
        "resource_name": "Test Video",
        "resource_description": "This is a test video",
        "resource_link": "test.mp4"
    }
    assert add_resources_to_module(payload) == "Resource added"

def test_get_course():
    course_id = 1
    assert get_course(course_id) == "Course object"

def test_save_changes_after_step():
    payload = {
        "course_id": 1,
        "module_id": 1,
        "reviewed_files": ["test1.jpg", "test2.jpg"]
    }
    assert save_changes_after_step(payload, 1) == "Changes saved"

def test_submit_module_for_step():
    payload = {
        "course_id": 1,
        "module_id": 1
    }
    assert submit_module_for_step(payload, 1, "in_content_generation_queue") == "Module submitted for content generation"

