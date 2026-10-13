import os

from system_folders import make_system_folder_checker


# Ищет пустые папки с учётом вложенности, исключений, защиты и отмены.
def find_empty_folders(
    root_path, excluded_paths=(), include_system=False, skipped_errors=None,
    progress_callback=None, cancel_event=None
):
    is_system_folder = make_system_folder_checker()
    if not include_system and is_system_folder(root_path):
        return []
    excluded = {
        os.path.normcase(os.path.abspath(path))
        for path in excluded_paths
    }
    empty_folders = []
    empty_paths = set()
    visited = []

    # Недоступные папки пропускаются; ошибки возвращаются интерфейсу для журнала.
    inaccessible_paths = set()

    # Пропускает недоступные папки и сохраняет ошибки доступа для журнала.
    def handle_error(error):
        if not isinstance(error, PermissionError):
            raise error
        if error.filename:
            inaccessible_paths.add(
                os.path.normcase(os.path.abspath(error.filename))
            )
        if skipped_errors is not None:
            skipped_errors.append(error)

    for current_path, folders, files in os.walk(
        root_path, topdown=True, onerror=handle_error
    ):
        # Отмена и счётчик поиска работают независимо от интерфейса.
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Поиск отменён")
        if progress_callback is not None:
            progress_callback(len(visited) + 1)
        all_folders = folders[:]

        folders[:] = [
            name for name in folders
            if os.path.normcase(
                os.path.abspath(os.path.join(current_path, name))
            ) not in excluded
            and (include_system or not is_system_folder(
                os.path.join(current_path, name)
            ))
        ]

        visited.append((current_path, all_folders, bool(files)))

    for current_path, folders, files in reversed(visited):
        if cancel_event is not None and cancel_event.is_set():
            raise InterruptedError("Поиск отменён")
        children_are_empty = all(
            os.path.normcase(
                os.path.abspath(os.path.join(current_path, name))
            ) in empty_paths
            for name in folders
        )

        # Папка с ошибкой доступа не считается пустой даже при неполном обходе.
        current_normalized = os.path.normcase(os.path.abspath(current_path))
        if (not files and children_are_empty
                and current_normalized not in inaccessible_paths):
            empty_folders.append(current_path)
            empty_paths.add(
                os.path.normcase(os.path.abspath(current_path))
            )

    return empty_folders
