"""
Проверка корректности введённых данных: путей, имён файлов,
размеров и типов содержимого, а также обработки ошибок.
"""
import os

import pytest

from validator import validate_folder, validate_file_parameters


# Существующий каталог принимается, функция возвращает абсолютный путь.
def test_existing_folder(tmp_path):
    assert validate_folder(str(tmp_path)) == os.path.abspath(tmp_path)


# Несуществующий каталог отклоняется.
def test_missing_folder(tmp_path):
    with pytest.raises(ValueError, match="Выберите существующую папку"):
        validate_folder(str(tmp_path / "missing"))


# Путь к файлу не считается путём к каталогу.
def test_file_instead_of_folder(tmp_path):
    file_path = tmp_path / "data.txt"
    file_path.write_text("data", encoding="utf-8")
    with pytest.raises(ValueError):
        validate_folder(str(file_path))


# Правильный размер вычисляется для всех поддерживаемых единиц.
@pytest.mark.parametrize("unit, expected", [
    ("КБ", 1024),
    ("МБ", 1024 ** 2),
    ("ГБ", 1024 ** 3),
])
def test_units(unit, expected):
    assert validate_file_parameters("test.bin", 1, unit, "Нули") == expected


# Оба типа содержимого принимаются валидатором.
@pytest.mark.parametrize("content_type", ["Нули", "Случайные данные"])
def test_content_types(content_type):
    assert validate_file_parameters("test.bin", 2, "КБ", content_type) == 2048


# Пустое и служебные имена запрещены.
@pytest.mark.parametrize("name", ["", ".", "..", "subdir/file.bin"])
def test_bad_names(name):
    with pytest.raises(ValueError, match="корректное имя"):
        validate_file_parameters(name, 1, "КБ", "Нули")


# Размер должен быть положительным целым числом, но не bool.
@pytest.mark.parametrize("size", [0, -1, 1.5, "2", True])
def test_bad_sizes(size):
    with pytest.raises(ValueError, match="положительным числом"):
        validate_file_parameters("test.bin", size, "КБ", "Нули")


# Неизвестные единицы измерения запрещены.
def test_unknown_unit():
    with pytest.raises(ValueError, match="Неизвестная единица"):
        validate_file_parameters("test.bin", 1, "байт", "Нули")


# Неизвестный вид содержимого запрещён.
def test_unknown_content():
    with pytest.raises(ValueError, match="Неизвестный тип"):
        validate_file_parameters("test.bin", 1, "КБ", "Текст")
