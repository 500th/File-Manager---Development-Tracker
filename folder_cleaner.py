import os

from system_folders import is_system_folder


# Системные папки удаляются только после явного разрешения из окна предупреждения.
def delete_empty_folders(root_path, selected_folders, allow_system=False):
    root = os.path.normcase(os.path.abspath(root_path))
    deleted = []
    errors = []

    folders = sorted(
        set(selected_folders),
        key=lambda path: path.count(os.sep),
        reverse=True
    )

    for folder in folders:
        path = os.path.abspath(folder)
        normalized_path = os.path.normcase(path)

        try:
            if (
                normalized_path == root
                or os.path.commonpath([root, normalized_path]) != root
            ):
                errors.append((path, "Нельзя удалить исходную папку или папку вне неё"))
                continue

            if is_system_folder(path) and not allow_system:
                errors.append((path, "Системная папка: требуется отдельное подтверждение"))
                continue

            os.rmdir(path)
            deleted.append(path)
        except (OSError, ValueError) as error:
            errors.append((path, str(error)))

    return deleted, errors
