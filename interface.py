import os
import queue
import threading
import time
import tkinter as tk

from tkinter import filedialog, messagebox, ttk

from operation_log import log_operation, log_error

from file_generator import generate_file
from folder_cleaner import delete_empty_folders
from folder_scanner import find_empty_folders
from validator import validate_folder
from system_folders import make_system_folder_checker


def create_interface():
    root = tk.Tk()
    root.title("Утилита файловой системы")
    # Окно располагается по центру рабочей области, с учётом панели задач.
    root.update_idletasks()
    left, top = 0, 0
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        area = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(area), 0):
            left, top = area.left, area.top
            screen_width = area.right - area.left
            screen_height = area.bottom - area.top

    width = min(820, screen_width - 40)
    height = min(720, screen_height - 80)
    x = left + (screen_width - width) // 2
    y = top + (screen_height - height - 40) // 2
    root.geometry(f"{width}x{height}+{x}+{y}")

    tabs = ttk.Notebook(root)
    tabs.pack(fill="both", expand=True)

    cleaner_tab = ttk.Frame(tabs, padding=10)
    generator_tab = ttk.Frame(tabs, padding=10)
    tabs.add(cleaner_tab, text="Очистка папок")
    tabs.add(generator_tab, text="Генератор файлов")

    # Первая вкладка: поиск и удаление пустых папок
    path_var = tk.StringVar()
    # Системные папки включаются пользователем; смена режима сбрасывает старый результат.
    include_system_var = tk.BooleanVar(value=False)

    def change_system_mode():
        folder_list.delete(0, tk.END)

    # Окно с перечнем системных папок и тремя вариантами действия.
    def warn_system_folders(paths):
        dialog = tk.Toplevel(root)
        dialog.title("Выбраны системные папки")
        dialog.geometry("760x350")
        dialog.transient(root)
        dialog.grab_set()
        choice = ["cancel"]

        ttk.Label(
            dialog,
            text="Удаление этих папок может нарушить работу Windows или программ.\n"
                 "Рекомендуется снять выделение системных папок.",
            wraplength=720
        ).pack(anchor="w", padx=15, pady=15)
        paths_box = tk.Listbox(dialog)
        paths_box.pack(fill="both", expand=True, padx=15)
        for path in paths:
            paths_box.insert(tk.END, path)

        def finish(value):
            choice[0] = value
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.pack(fill="x", padx=15, pady=15)
        remove_button = ttk.Button(
            buttons, text="Снять выделение системных папок",
            command=lambda: finish("deselect")
        )
        remove_button.pack(side="left")
        ttk.Button(buttons, text="Отмена", command=lambda: finish("cancel")).pack(
            side="left", padx=10
        )
        ttk.Button(
            buttons, text="Продолжить удаление", command=lambda: finish("continue")
        ).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish("cancel"))
        dialog.bind("<Escape>", lambda event: finish("cancel"))
        remove_button.focus_set()
        root.wait_window(dialog)
        return choice[0]

    def choose_folder():
        folder = filedialog.askdirectory()
        if folder:
            path_var.set(folder)
            folder_list.delete(0, tk.END)
            exclusion_list.delete(0, tk.END)

    # Фоновый поиск передаёт результаты через очередь; виджеты меняет только Tk.
    scan_updates = queue.Queue()
    scan_cancel = threading.Event()
    scanning = False
    # Удаление использует отдельную очередь и событие отмены.
    delete_updates = queue.Queue()
    delete_cancel = threading.Event()
    deleting = False
    closing = False
    scan_status = tk.StringVar(value="Поиск не запущен")

    def set_scan_controls(active):
        state = "disabled" if active else "normal"
        for widget in scan_controls:
            widget.config(state=state)
        scan_cancel_button.config(state="normal" if active else "disabled")
        # Индикатор виден только пока идёт поиск или заполнение результата.
        if active:
            scan_progress.config(mode="indeterminate")
            scan_progress.pack(fill="x", pady=5, before=scan_status_label)
            scan_progress.start(12)
        else:
            scan_progress.stop()
            scan_progress.pack_forget()

    def cancel_scan():
        scan_cancel.set()
        scan_cancel_button.config(state="disabled")
        scan_status.set("Отмена поиска...")

    def finish_scan(found, skipped, path, checked):
        nonlocal scanning
        # Большой результат добавляется порциями, чтобы окно продолжало отвечать.
        def insert_batch(offset=0):
            nonlocal scanning
            batch = found[offset:offset + 300]
            if batch:
                folder_list.insert(tk.END, *batch)
            if offset + 300 < len(found):
                root.after(1, insert_batch, offset + 300)
                return
            scanning = False
            set_scan_controls(False)
            scan_status.set(f"Поиск завершён. Проверено: {checked}; найдено: {len(found)}")
            # Итог поиска завершает группу записей пустой строкой.
            for error in skipped:
                log_error(f"Папка пропущена при сканировании {path}: {error}")
            log_operation(f"Поиск пустых папок: {path}; найдено: {len(found)}\n")
            if skipped:
                messagebox.showwarning(
                    "Результат поиска",
                    f"Поиск завершён. Найдено пустых вложенных папок: {len(found)}.\n"
                    f"Папок без доступа: {len(skipped)}.\nПодробности в operations.log."
                )
            elif not found:
                messagebox.showinfo("Результат", "Пустые вложенные папки не найдены.")
        scan_status.set("Заполнение списка...")
        scan_cancel_button.config(state="disabled")
        insert_batch()

    def check_scan_updates():
        nonlocal scanning
        try:
            while True:
                kind, value = scan_updates.get_nowait()
                if kind == "progress":
                    if not scan_cancel.is_set():
                        scan_status.set(f"Идёт поиск. Проверено папок: {value}")
                elif kind == "done":
                    finish_scan(*value)
                    return
                elif kind in ("cancelled", "error"):
                    scanning = False
                    set_scan_controls(False)
                    if kind == "cancelled":
                        scan_status.set("Поиск отменён")
                        log_operation("Поиск пустых папок отменён")
                    else:
                        scan_status.set("Ошибка поиска")
                        log_error(f"Ошибка сканирования: {value}")
                        messagebox.showerror("Ошибка сканирования", value)
                    return
        except queue.Empty:
            pass
        if scanning:
            root.after(100, check_scan_updates)

    def scan_folders():
        nonlocal scanning
        if scanning or deleting:
            return
        try:
            path = validate_folder(path_var.get().strip())
        except ValueError as error:
            messagebox.showerror("Ошибка", str(error))
            return
        excluded = exclusion_list.get(0, tk.END)
        include_system = include_system_var.get()
        folder_list.delete(0, tk.END)
        scan_cancel.clear()
        scanning = True
        scan_status.set("Идёт поиск...")
        set_scan_controls(True)

        def worker():
            skipped = []
            checked = 0
            last_update = 0

            def report(count):
                nonlocal checked, last_update
                checked = count
                now = time.monotonic()
                if now - last_update >= 0.1:
                    scan_updates.put(("progress", count))
                    last_update = now

            try:
                found = find_empty_folders(
                    path, excluded, include_system=include_system,
                    skipped_errors=skipped, progress_callback=report,
                    cancel_event=scan_cancel
                )
                root_path = os.path.normcase(os.path.abspath(path))
                found = [folder for folder in found
                         if os.path.normcase(os.path.abspath(folder)) != root_path]
                if scan_cancel.is_set():
                    raise InterruptedError()
            except InterruptedError:
                scan_updates.put(("cancelled", None))
            except Exception as error:
                scan_updates.put(("error", str(error)))
            else:
                scan_updates.put(("done", (found, skipped, path, checked)))

        threading.Thread(target=worker, daemon=True).start()
        root.after(100, check_scan_updates)

    # Виджеты обновляет основной поток; удаление и журнал выполняются в рабочем.
    def set_delete_controls(active):
        state = "disabled" if active else "normal"
        for widget in (*scan_controls, folder_list, exclusion_list):
            widget.config(state=state)
        delete_cancel_button.config(state="normal" if active else "disabled")
        if active:
            scan_progress.config(mode="determinate", maximum=100, value=0)
            scan_progress.pack(fill="x", pady=5, before=scan_status_label)
        else:
            scan_progress.pack_forget()

    def cancel_deletion():
        if deleting:
            delete_cancel.set()
            delete_cancel_button.config(state="disabled")
            scan_status.set("Отмена удаления после текущей папки...")

    def finish_deletion(deleted, errors, processed, total, cancelled, selected_indices):
        deleted_paths = {os.path.normcase(os.path.abspath(path)) for path in deleted}
        # Соседние удалённые строки убираются одним вызовом, группы — порциями.
        ranges = []
        for index in selected_indices:
            path = os.path.normcase(os.path.abspath(folder_list.get(index)))
            if path in deleted_paths:
                if ranges and index == ranges[-1][1] + 1:
                    ranges[-1][1] = index
                else:
                    ranges.append([index, index])
        ranges.reverse()
        scan_status.set("Обновление списка...")
        delete_cancel_button.config(state="disabled")

        def remove_batch(offset=0):
            nonlocal deleting
            folder_list.config(state="normal")
            for first, last in ranges[offset:offset + 100]:
                folder_list.delete(first, last)
            folder_list.config(state="disabled")
            if offset + 100 < len(ranges):
                root.after(1, remove_batch, offset + 100)
                return
            deleting = False
            set_delete_controls(False)
            title = "Удаление отменено" if cancelled else "Удаление завершено"
            scan_status.set(
                f"{title}. Обработано: {processed} из {total}; "
                f"удалено: {len(deleted)}; ошибок: {len(errors)}"
            )
            if closing:
                root.destroy()
                return
            result = (f"Обработано папок: {processed} из {total}.\n"
                      f"Удалено: {len(deleted)}. Ошибок: {len(errors)}.")
            if cancelled:
                result += "\nУже удалённые папки не восстанавливаются."
            if errors:
                result += "\nПодробности записаны в operations.log."
                messagebox.showwarning(title, result)
            else:
                messagebox.showinfo(title, result)

        remove_batch()

    def check_delete_updates():
        nonlocal deleting
        try:
            while True:
                kind, value = delete_updates.get_nowait()
                if kind == "progress":
                    processed, total, removed, errors = value
                    scan_progress["value"] = processed * 100 / total if total else 0
                    if not delete_cancel.is_set():
                        scan_status.set(
                            f"Обработано: {processed} из {total}; "
                            f"удалено: {removed}; ошибок: {errors}"
                        )
                elif kind == "logging":
                    delete_cancel_button.config(state="disabled")
                    scan_status.set("Сохранение журнала удаления...")
                elif kind == "done":
                    finish_deletion(*value)
                    return
                elif kind == "error":
                    deleting = False
                    set_delete_controls(False)
                    scan_status.set("Ошибка удаления")
                    if closing:
                        root.destroy()
                        return
                    messagebox.showerror("Ошибка удаления", value)
                    return
        except queue.Empty:
            pass
        if deleting:
            root.after(100, check_delete_updates)

    def delete_selected():
        nonlocal deleting
        if scanning or deleting:
            return
        indices = folder_list.curselection()

        if not indices:
            messagebox.showwarning("Удаление", "Сначала выберите папки в списке.")
            return

        selected = [folder_list.get(index) for index in indices]

        # Защищённые корни вычисляются один раз для всех выбранных папок.
        is_system = make_system_folder_checker()
        system_paths = [path for path in selected if is_system(path)]
        allow_system = False
        if system_paths:
            choice = warn_system_folders(system_paths)
            if choice == "deselect":
                system_paths = set(system_paths)
                for index in indices:
                    if folder_list.get(index) in system_paths:
                        folder_list.selection_clear(index)
                log_operation("Снято выделение системных папок")
                return
            if choice != "continue":
                return
            allow_system = True
            log_operation("Пользователь разрешил удаление выбранных системных папок")

        if not messagebox.askyesno(
                "Подтверждение удаления",
                f"Удалить выбранные папки ({len(selected)})?\n"
                "Они не попадут в корзину."
        ):
            return

        root_path = path_var.get().strip()
        delete_cancel.clear()
        deleting = True
        set_delete_controls(True)
        scan_status.set(f"Удаление папок: 0 из {len(selected)}...")

        def worker():
            processed = 0
            total = len(set(selected))
            last_update = 0

            def report(count, count_total, removed, errors):
                nonlocal processed, last_update
                processed = count
                now = time.monotonic()
                if now - last_update >= 0.1 or count == count_total:
                    delete_updates.put(("progress", (count, count_total, removed, errors)))
                    last_update = now

            try:
                deleted, errors = delete_empty_folders(
                    root_path, selected, allow_system=allow_system,
                    progress_callback=report, cancel_event=delete_cancel
                )
                cancelled = delete_cancel.is_set() and processed < total
                delete_updates.put(("logging", None))
                for path in deleted:
                    log_operation(f"Удалена пустая папка: {path}")
                for path, error in errors:
                    log_error(f"Не удалось удалить {path}: {error}")
                outcome = "Удаление отменено" if cancelled else "Удаление завершено"
                log_operation(
                    f"{outcome}: {root_path}; обработано: {processed} из {total}; "
                    f"удалено пустых папок: {len(deleted)}; ошибок: {len(errors)}\n"
                )
            except Exception as error:
                log_error(f"Ошибка удаления папок: {error}")
                delete_updates.put(("error", str(error)))
            else:
                delete_updates.put(("done", (deleted, errors, processed, total, cancelled, indices)))

        threading.Thread(target=worker).start()
        root.after(100, check_delete_updates)

    def select_all_folders():
        folder_list.selection_set(0, tk.END)

    ttk.Label(cleaner_tab, text="Папка для проверки:").pack(anchor="w")
    path_entry = ttk.Entry(cleaner_tab, textvariable=path_var)
    path_entry.pack(fill="x", pady=5)
    choose_button = ttk.Button(cleaner_tab, text="Выбрать папку", command=choose_folder)
    choose_button.pack(anchor="w")

    # Галочка и пояснение размещены без отдельной рамки и заголовка.
    system_check = ttk.Checkbutton(
        cleaner_tab, text="Включить системные папки",
        variable=include_system_var, command=change_system_mode
    )
    system_check.pack(anchor="w", pady=(10, 0))
    ttk.Label(
        cleaner_tab,
        text="По умолчанию пропускаются Windows, Windows.old, Program Files,\n"
             "Program Files (x86), ProgramData и AppData пользовательских профилей.",
        wraplength=740
    ).pack(anchor="w", pady=(4, 10))

    def add_exclusion():
        if not os.path.isdir(path_var.get().strip()):
            messagebox.showerror("Ошибка", "Сначала выберите папку для проверки.")
            return

        folder = filedialog.askdirectory(initialdir=path_var.get().strip())
        if not folder:
            return

        if os.path.normcase(os.path.abspath(folder)) == os.path.normcase(
            os.path.abspath(path_var.get().strip())
        ):
            messagebox.showerror("Ошибка", "Нельзя исключить исходную папку.")
            return

        if folder not in exclusion_list.get(0, tk.END):
            exclusion_list.insert(tk.END, folder)
            folder_list.delete(0, tk.END)

    def remove_exclusion():
        for index in reversed(exclusion_list.curselection()):
            exclusion_list.delete(index)
        folder_list.delete(0, tk.END)

    ttk.Label(cleaner_tab, text="Исключённые папки:").pack(anchor="w")
    exclusion_list = tk.Listbox(cleaner_tab, height=2, exportselection=False)
    exclusion_list.pack(fill="x", pady=5)

    exclusion_buttons = ttk.Frame(cleaner_tab)
    exclusion_buttons.pack(fill="x")
    add_exclusion_button = ttk.Button(
        exclusion_buttons, text="Добавить исключение", command=add_exclusion
    )
    add_exclusion_button.pack(side="left")
    remove_exclusion_button = ttk.Button(
        exclusion_buttons, text="Убрать исключение", command=remove_exclusion
    )
    remove_exclusion_button.pack(side="left", padx=5)

    search_buttons = ttk.Frame(cleaner_tab)
    search_buttons.pack(fill="x", pady=(8, 0))
    scan_button = ttk.Button(search_buttons, text="Найти пустые папки", command=scan_folders)
    scan_button.pack(side="left")
    scan_cancel_button = ttk.Button(
        search_buttons, text="Отменить поиск", command=cancel_scan, state="disabled"
    )
    scan_cancel_button.pack(side="left", padx=5)
    scan_progress = ttk.Progressbar(cleaner_tab, mode="indeterminate")
    scan_status_label = ttk.Label(cleaner_tab, textvariable=scan_status)
    scan_status_label.pack(anchor="w", pady=(5, 5))

    # Обе полосы прокрутки позволяют просматривать большой список и длинные пути.
    results = ttk.Frame(cleaner_tab)
    results.pack(fill="both", expand=True)
    results.rowconfigure(0, weight=1)
    results.columnconfigure(0, weight=1)
    folder_list = tk.Listbox(results, selectmode=tk.EXTENDED, exportselection=False)
    folder_list.grid(row=0, column=0, sticky="nsew")
    vertical_scroll = ttk.Scrollbar(results, orient="vertical", command=folder_list.yview)
    vertical_scroll.grid(row=0, column=1, sticky="ns")
    horizontal_scroll = ttk.Scrollbar(results, orient="horizontal", command=folder_list.xview)
    horizontal_scroll.grid(row=1, column=0, sticky="ew")
    folder_list.config(yscrollcommand=vertical_scroll.set, xscrollcommand=horizontal_scroll.set)

    bottom_buttons = ttk.Frame(cleaner_tab)
    bottom_buttons.pack(fill="x", pady=8)
    select_button = ttk.Button(bottom_buttons, text="Выбрать всё", command=select_all_folders)
    select_button.pack(side="left")
    delete_button = ttk.Button(bottom_buttons, text="Удалить выбранные", command=delete_selected)
    delete_button.pack(side="right")
    delete_cancel_button = ttk.Button(
        bottom_buttons, text="Отменить удаление", command=cancel_deletion, state="disabled"
    )
    delete_cancel_button.pack(side="right", padx=5)
    scan_controls = (path_entry, choose_button, system_check, add_exclusion_button,
                     remove_exclusion_button, scan_button, select_button, delete_button)

    # Вторая вкладка: создание тестовых файлов
    output_folder_var = tk.StringVar()
    file_name_var = tk.StringVar()
    file_size_var = tk.StringVar(value="1")
    unit_var = tk.StringVar(value="КБ")
    content_var = tk.StringVar(value="Нули")
    status_var = tk.StringVar(value="Ожидание")

    updates = queue.Queue()
    cancel_event = None
    running = False

    def choose_output_folder():
        folder = filedialog.askdirectory()
        if folder:
            output_folder_var.set(folder)

    def finish_operation():
        nonlocal running
        running = False
        create_button.config(state="normal")
        cancel_button.config(state="disabled")

    def check_updates():
        try:
            while True:
                kind, value = updates.get_nowait()

                if kind == "progress":
                    progress_bar["value"] = value
                    status_var.set(f"Создано: {value}%")
                elif kind == "done":
                    finish_operation()
                    status_var.set("Файл создан")
                    log_operation(f"Создан файл: {value}")
                    messagebox.showinfo("Готово", f"Файл создан:\n{value}")
                elif kind == "cancelled":
                    finish_operation()
                    status_var.set("Создание отменено")
                    log_operation("Создание файла отменено")
                elif kind == "error":
                    finish_operation()
                    status_var.set("Ошибка")
                    log_error(f"Ошибка создания файла: {value}")
                    messagebox.showerror("Ошибка создания файла", value)
        except queue.Empty:
            pass

        if running:
            root.after(50, check_updates)

    def cancel_creation():
        if cancel_event is not None:
            cancel_event.set()
            cancel_button.config(state="disabled")
            status_var.set("Отмена...")

    def create_file():
        nonlocal cancel_event, running

        if running:
            return

        folder = output_folder_var.get().strip()
        name = file_name_var.get().strip()
        unit = unit_var.get()
        content_type = content_var.get()
        target = os.path.join(folder, name)

        try:
            size = int(file_size_var.get())
        except ValueError:
            messagebox.showerror("Ошибка", "Размер должен быть целым числом.")
            return

        overwrite = False
        if os.path.isfile(target):
            overwrite = messagebox.askyesno(
                "Файл уже существует",
                f"Файл {name} уже существует. Перезаписать его?"
            )
            if not overwrite:
                return

        cancel_event = threading.Event()
        running = True
        progress_bar["value"] = 0
        status_var.set("Создание файла...")
        create_button.config(state="disabled")
        cancel_button.config(state="normal")

        def worker():
            try:
                path = generate_file(
                    folder, name, size, unit, content_type,
                    overwrite=overwrite,
                    progress_callback=lambda done, total: updates.put(
                        ("progress", done * 100 // total)
                    ),
                    cancel_event=cancel_event
                )
            except InterruptedError:
                updates.put(("cancelled", None))
            except (ValueError, OSError) as error:
                updates.put(("error", str(error)))
            else:
                updates.put(("done", path))

        threading.Thread(target=worker).start()
        root.after(50, check_updates)

    ttk.Label(generator_tab, text="Папка для сохранения:").pack(anchor="w")
    ttk.Entry(generator_tab, textvariable=output_folder_var).pack(fill="x", pady=5)
    ttk.Button(
        generator_tab, text="Выбрать папку", command=choose_output_folder
    ).pack(anchor="w")

    ttk.Label(generator_tab, text="Имя файла:").pack(anchor="w", pady=(15, 0))
    ttk.Entry(generator_tab, textvariable=file_name_var).pack(fill="x", pady=5)

    ttk.Label(generator_tab, text="Размер файла:").pack(anchor="w", pady=(10, 0))
    ttk.Entry(generator_tab, textvariable=file_size_var).pack(fill="x", pady=5)

    ttk.Label(generator_tab, text="Единица измерения:").pack(anchor="w")
    ttk.Combobox(
        generator_tab, textvariable=unit_var,
        values=("КБ", "МБ", "ГБ"), state="readonly"
    ).pack(fill="x", pady=5)

    ttk.Label(generator_tab, text="Содержимое файла:").pack(anchor="w")
    ttk.Combobox(
        generator_tab, textvariable=content_var,
        values=("Нули", "Случайные данные"), state="readonly"
    ).pack(fill="x", pady=5)

    create_button = ttk.Button(
        generator_tab, text="Создать файл", command=create_file
    )
    create_button.pack(anchor="e", pady=(15, 5))

    progress_bar = ttk.Progressbar(generator_tab, maximum=100)
    progress_bar.pack(fill="x", pady=5)

    ttk.Label(generator_tab, textvariable=status_var).pack(anchor="w")

    cancel_button = ttk.Button(
        generator_tab, text="Отмена", command=cancel_creation,
        state="disabled"
    )
    cancel_button.pack(anchor="e", pady=5)

    # При закрытии во время удаления сначала останавливаем его и сохраняем итог.
    def close_window():
        nonlocal closing
        if deleting:
            closing = True
            cancel_deletion()
        else:
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", close_window)
    root.mainloop()
