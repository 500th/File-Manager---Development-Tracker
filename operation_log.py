import logging
from pathlib import Path


logger = logging.getLogger("kpo")
logger.setLevel(logging.INFO)

if not logger.handlers:
    log_path = Path(__file__).with_name("operations.log")
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    logger.addHandler(handler)


# Записывает информационное сообщение об операции в журнал.
def log_operation(message):
    logger.info(message)


# Записывает сообщение об ошибке в журнал.
def log_error(message):
    logger.error(message)