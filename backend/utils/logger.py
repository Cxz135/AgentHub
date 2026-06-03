#logger.py


import logging
import os
from datetime import datetime
from backend.utils.path_tool import get_abs_path

LOG_ROOT = get_abs_path("logs")

os.makedirs(LOG_ROOT, exist_ok=True)

DEFAULT_LOGGING_FORMAT = logging.Formatter(
    '%(asctime)s-%(name)-s %(levelname)s-%(filename)s:%(lineno)d-%(message)s',
)

def get_logger(
        name: str = 'core',
        console_level: int = logging.INFO,
        file_level: int = logging.DEBUG,
        log_file = None
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers: return logger

    consoler_handler = logging.StreamHandler()
    consoler_handler.setLevel(console_level)
    consoler_handler.setFormatter(DEFAULT_LOGGING_FORMAT)
    logger.addHandler(consoler_handler)

    if not log_file:
        log_file = os.path.join(LOG_ROOT, f'{name}_{datetime.now().strftime("%Y%m%d-%H%M")}.log')

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(file_level)
    file_handler.setFormatter(DEFAULT_LOGGING_FORMAT)
    logger.addHandler(file_handler)

    return logger


logger = get_logger()
