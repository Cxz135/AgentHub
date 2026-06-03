#path_tool.py


import os

def get_path() -> str:

    current_file = os.path.abspath(__file__)

    current_dir = os.path.dirname(current_file)

    project_root = os.path.dirname(current_dir)

    return project_root

def get_abs_path(path: str) -> str:

    return os.path.join(get_path(), path)