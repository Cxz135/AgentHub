#file_handler.py


import os, hashlib



from backend.utils.logger import logger
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader, TextLoader


def get_file_md5_hex(filepath: str):

    if not os.path.exists(filepath) or not os.path.isfile(filepath):
        logger.error(f"File not exist or file not found: {filepath}")
        return

    md5_obj = hashlib.md5()
    chunk_size = 512 * 512
    try:
        with open(filepath, "rb") as f:
            while chunk := f.read(chunk_size):
                md5_obj.update(chunk)
            md5_hex = md5_obj.hexdigest()
            return md5_hex
    except Exception as e:
        logger.error(f"File not exist or file not found: {filepath}")
        return None

def listdir_with_allowed_type(path: str, allowed_types: tuple[str]):
    files = []
    if not os.path.isdir(path):
        logger.error(f"Path {path} is not a directory")
        return allowed_types
    for f in os.listdir(path):
        if f.endswith(allowed_types):
            files.append(os.path.join(path, f))

    return tuple(files)

def pdf_loader(file_path: str) -> list[Document]:
    return PyPDFLoader(file_path).load()

def txt_loader(file_path: str) -> list[Document]:
    return TextLoader(file_path).load()