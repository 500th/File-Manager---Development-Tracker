import logging
import os
from pathlib import Path

# Журнал хранится вне временной папки упакованного приложения.
if os.name == "nt":
    log_dir = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "File_Manager_Utility"
else:
    log_dir = Path.home() / ".local" / "state" / "File_Manager_Utility"
log_dir.mkdir(parents=True, exist_ok=True)
log_path = log_dir / "operations.log"

logger = logging.getLogger("File_Manager_Utility")
logger.setLevel(logging.INFO)

if not logger.handlers:
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
