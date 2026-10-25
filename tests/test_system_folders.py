"""
Проверка распознавания системных и обычных каталогов,
нормализации путей и определения защищённых папок.
"""
import ntpath
import system_folders


# Защищённый корень распознаётся.
def test_protected_root(monkeypatch):
    monkeypatch.setattr('system_folders.get_system_folders', lambda: [r'C:\Windows'])
    assert system_folders.make_system_folder_checker()(r'C:\Windows')


# Вложенный каталог защищённого корня тоже распознаётся.
def test_protected_child(monkeypatch):
    monkeypatch.setattr('system_folders.get_system_folders', lambda: [r'C:\Windows'])
    assert system_folders.is_system_folder(r'C:\Windows\Temp')


# Обычный каталог не определяется как защищённый.
def test_unprotected_folder(monkeypatch):
    monkeypatch.setattr('system_folders.get_system_folders', lambda: [r'C:\Windows'])
    assert not system_folders.is_system_folder(r'C:\MyProjects')


# Похожее начало имени не создаёт ложного совпадения.
def test_similar_name_not_protected(monkeypatch):
    monkeypatch.setattr('system_folders.get_system_folders', lambda: [r'C:\Windows'])
    assert not system_folders.is_system_folder(r'C:\WindowsBackup')


# Сравнение не зависит от регистра Windows-пути.
def test_case_insensitive(monkeypatch):
    monkeypatch.setattr('system_folders.get_system_folders', lambda: [r'C:\Windows'])
    assert system_folders.is_system_folder(r'c:\WINDOWS\TEMP')


# Каталог на другом диске не считается вложенным.
def test_different_drive(monkeypatch):
    monkeypatch.setattr('system_folders.get_system_folders', lambda: [r'C:\Windows'])
    assert not system_folders.is_system_folder(r'D:\Windows')


# Список системных корней содержит базовые каталоги Windows.
def test_default_roots(monkeypatch):
    monkeypatch.setenv('SystemDrive', 'C:')
    roots = system_folders.get_system_folders()
    normalized = {ntpath.normcase(root) for root in roots}
    assert ntpath.normcase(r'C:\Windows') in normalized
    assert ntpath.normcase(r'C:\ProgramData') in normalized
