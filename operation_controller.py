import os
import queue
import threading
import time

from file_generator import generate_file
from folder_cleaner import delete_empty_folders
from folder_scanner import find_empty_folders
from operation_log import log_error, log_operation
from system_folders import make_system_folder_checker
from validator import validate_folder


# Управление операциями без Tkinter: потоки, отмена, результаты и журнал.
class OperationController:
    def __init__(self):
        names = ("scan", "delete", "generation")
        self._updates = {name: queue.Queue() for name in names}
        self._cancel = {name: threading.Event() for name in names}
        self._running = {name: False for name in names}

    def _start(self, name, worker, daemon=False):
        if self._running[name] or (
            name in ("scan", "delete")
            and (self._running["scan"] or self._running["delete"])
        ):
            raise RuntimeError("Операция уже выполняется.")
        self._poll(name)
        self._cancel[name].clear()
        self._running[name] = True

        def run():
            try:
                kind, value = worker()
            except Exception as error:
                prefix = {
                    "scan": "Ошибка сканирования",
                    "delete": "Ошибка удаления папок",
                    "generation": "Ошибка создания файла",
                }[name]
                log_error(f"{prefix}: {error}")
                kind, value = "error", str(error)
            finally:
                self._running[name] = False
            self._updates[name].put((kind, value))

        try:
            threading.Thread(target=run, daemon=daemon).start()
        except Exception:
            self._running[name] = False
            raise

    def _poll(self, name):
        updates = []
        while True:
            try:
                updates.append(self._updates[name].get_nowait())
            except queue.Empty:
                return updates

    def poll_scan_updates(self):
        return self._poll("scan")

    def poll_delete_updates(self):
        return self._poll("delete")

    def poll_generation_updates(self):
        return self._poll("generation")

    @property
    def scan_cancel_requested(self):
        return self._cancel["scan"].is_set()

    @property
    def delete_cancel_requested(self):
        return self._cancel["delete"].is_set()

    def cancel_scan(self):
        self._cancel["scan"].set()

    def cancel_deletion(self):
        self._cancel["delete"].set()

    def cancel_generation(self):
        self._cancel["generation"].set()

    def get_system_paths(self, paths):
        is_system = make_system_folder_checker()
        return [path for path in paths if is_system(path)]

    def record_system_choice(self, choice):
        if choice == "deselect":
            log_operation("Снято выделение системных папок")
        elif choice == "continue":
            log_operation("Пользователь разрешил удаление выбранных системных папок")

    def start_scan(self, root_path, excluded_paths=(), include_system=False):
        path = validate_folder(root_path)
        excluded = tuple(excluded_paths)

        def worker():
            skipped = []
            checked = 0
            last_update = 0

            def report(count):
                nonlocal checked, last_update
                checked = count
                now = time.monotonic()
                if now - last_update >= 0.1:
                    self._updates["scan"].put(("progress", count))
                    last_update = now

            try:
                found = find_empty_folders(
                    path, excluded, include_system=include_system,
                    skipped_errors=skipped, progress_callback=report,
                    cancel_event=self._cancel["scan"]
                )
                root = os.path.normcase(os.path.abspath(path))
                found = [folder for folder in found
                         if os.path.normcase(os.path.abspath(folder)) != root]
                if self.scan_cancel_requested:
                    raise InterruptedError()
            except InterruptedError:
                log_operation("Поиск пустых папок отменён")
                return "cancelled", None
            for error in skipped:
                log_error(f"Папка пропущена при сканировании {path}: {error}")
            log_operation(f"Поиск пустых папок: {path}; найдено: {len(found)}\n")
            return "done", (found, skipped, path, checked)

        self._start("scan", worker, daemon=True)

    def start_deletion(self, root_path, selected_folders, allow_system=False):
        selected = tuple(selected_folders)

        def worker():
            processed = 0
            total = len(set(selected))
            last_update = 0

            def report(count, count_total, removed, errors):
                nonlocal processed, last_update
                processed = count
                now = time.monotonic()
                if now - last_update >= 0.1 or count == count_total:
                    self._updates["delete"].put(
                        ("progress", (count, count_total, removed, errors))
                    )
                    last_update = now

            deleted, errors = delete_empty_folders(
                root_path, selected, allow_system=allow_system,
                progress_callback=report, cancel_event=self._cancel["delete"]
            )
            cancelled = self.delete_cancel_requested and processed < total
            self._updates["delete"].put(("logging", None))
            for path in deleted:
                log_operation(f"Удалена пустая папка: {path}")
            for path, error in errors:
                log_error(f"Не удалось удалить {path}: {error}")
            outcome = "Удаление отменено" if cancelled else "Удаление завершено"
            log_operation(
                f"{outcome}: {root_path}; обработано: {processed} из {total}; "
                f"удалено пустых папок: {len(deleted)}; ошибок: {len(errors)}\n"
            )
            return "done", (deleted, errors, processed, total, cancelled)

        self._start("delete", worker)

    def start_generation(self, folder, name, size, unit, content_type, overwrite=False):
        def worker():
            try:
                path = generate_file(
                    folder, name, size, unit, content_type,
                    overwrite=overwrite,
                    progress_callback=lambda done, total: self._updates["generation"].put(
                        ("progress", done * 100 // total)
                    ),
                    cancel_event=self._cancel["generation"]
                )
            except InterruptedError:
                log_operation("Создание файла отменено")
                return "cancelled", None
            log_operation(f"Создан файл: {path}")
            return "done", path

        self._start("generation", worker)
