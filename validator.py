import os


# Проверяет существование папки и возвращает её абсолютный путь.
def validate_folder(path):
    if not os.path.isdir(path):
        raise ValueError("Выберите существующую папку.")
    return os.path.abspath(path)


# Проверяет имя, размер и содержимое файла, возвращает размер в байтах.
def validate_file_parameters(name, size, unit, content_type):
    if not name or name in (".", "..") or os.path.basename(name) != name:
        raise ValueError("Укажите корректное имя файла")

    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ValueError("Размер должен быть целым положительным числом")

    units = {"КБ": 1024, "МБ": 1024 ** 2, "ГБ": 1024 ** 3}
    if unit not in units:
        raise ValueError("Неизвестная единица измерения")

    if content_type not in ("Нули", "Случайные данные"):
        raise ValueError("Неизвестный тип содержимого")

    return size * units[unit]