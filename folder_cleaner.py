import os

from system_folders import make_system_folder_checker


# Удаляет выбранные пустые папки с проверкой защиты, прогрессом и отменой.
def delete_empty_folders(root_path, selected_folders, allow_system=False,
                         progress_callback=None, cancel_event=None):
    root = os.path.normcase(os.path.abspath(root_path))
    deleted = []
    errors = []

    folders = sorted(
        set(selected_folders),
        key=lambda path: path.count(os.sep),
        reverse=True
    )

    # Корни готовятся один раз; отмена проверяется перед следующей папкой.
    is_system = make_system_folder_checker() if not allow_system else None
    for processed, folder in enumerate(folders, start=1):
        if cancel_event is not None and cancel_event.is_set():
            break
        path = os.path.abspath(folder)
        normalized_path = os.path.normcase(path)

        try:
            if (
                normalized_path == root
                or os.path.commonpath([root, normalized_path]) != root
            ):
                errors.append((path, "Нельзя удалить исходную папку или папку вне неё"))
                continue

            if not allow_system and is_system(path):
                errors.append((path, "Системная папка: требуется отдельное подтверждение"))
                continue

            os.rmdir(path)
            deleted.append(path)
        except (OSError, ValueError) as error:
            errors.append((path, str(error)))
        finally:
            if progress_callback is not None:
                progress_callback(processed, len(folders), len(deleted), len(errors))

    return deleted, errors
