#config_handler.py


import yaml
from backend.utils.path_tool import get_abs_path

def load_chroma_config(config_path: str = get_abs_path('config/chroma.yaml'), encoding='utf-8'):
    with open(config_path, 'r', encoding=encoding) as f:
        return yaml.load(f, Loader=yaml.FullLoader)






chroma_config = load_chroma_config()