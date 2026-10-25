"""
Проверка удаления пустых папок, защиты каталогов,
обработки ошибок, прогресса и отмены удаления.
"""
from threading import Event
import pytest
from folder_cleaner import delete_empty_folders


# Подменяем защиту: временные каталоги pytest в Windows лежат внутри AppData.
@pytest.fixture(autouse=True)
def ordinary_test_folders(monkeypatch):
    monkeypatch.setattr('folder_cleaner.make_system_folder_checker', lambda: lambda path: False)


# Пустая вложенная папка успешно удаляется.
def test_delete_empty(tmp_path):
    child = tmp_path / 'empty'
    child.mkdir()
    deleted, errors = delete_empty_folders(str(tmp_path), [str(child)])
    assert deleted == [str(child)] and errors == [] and not child.exists()


# Непустую папку нельзя удалить.
def test_nonempty_is_preserved(tmp_path):
    child = tmp_path / 'data'
    child.mkdir()
    (child / 'keep.txt').write_text('keep')
    deleted, errors = delete_empty_folders(str(tmp_path), [str(child)])
    assert not deleted and len(errors) == 1 and child.exists()


# Корневая папка всегда сохраняется.
def test_root_is_preserved(tmp_path):
    deleted, errors = delete_empty_folders(str(tmp_path), [str(tmp_path)])
    assert not deleted and len(errors) == 1 and tmp_path.exists()


# Каталог вне выбранного корня нельзя удалять.
def test_outside_root(tmp_path):
    root = tmp_path / 'root'
    outside = tmp_path / 'outside'
    root.mkdir()
    outside.mkdir()
    deleted, errors = delete_empty_folders(str(root), [str(outside)])
    assert not deleted and len(errors) == 1 and outside.exists()


# Дочерний каталог удаляется раньше родительского.
def test_nested_delete(tmp_path):
    parent = tmp_path / 'parent'
    child = parent / 'child'
    child.mkdir(parents=True)
    deleted, errors = delete_empty_folders(str(tmp_path), [str(parent), str(child)])
    assert deleted == [str(child), str(parent)] and not errors


# Дубликаты выбранных путей обрабатываются один раз.
def test_duplicate_selection(tmp_path):
    child = tmp_path / 'one'
    child.mkdir()
    deleted, errors = delete_empty_folders(str(tmp_path), [str(child), str(child)])
    assert deleted == [str(child)] and not errors


# Защищённый каталог нельзя удалить без разрешения.
def test_protected_rejected(tmp_path, monkeypatch):
    child = tmp_path / 'protected'
    child.mkdir()
    monkeypatch.setattr('folder_cleaner.make_system_folder_checker', lambda: lambda path: True)
    deleted, errors = delete_empty_folders(str(tmp_path), [str(child)])
    assert deleted == [] and len(errors) == 1 and child.exists()


# Явное разрешение снимает блокировку защищённого каталога.
def test_protected_allowed(tmp_path, monkeypatch):
    child = tmp_path / 'protected'
    child.mkdir()
    monkeypatch.setattr('folder_cleaner.make_system_folder_checker', lambda: lambda path: True)
    deleted, errors = delete_empty_folders(str(tmp_path), [str(child)], allow_system=True)
    assert deleted == [str(child)] and errors == []


# Прогресс показывает количество обработанных каталогов.
def test_progress(tmp_path):
    child = tmp_path / 'empty'
    child.mkdir()
    updates = []
    delete_empty_folders(str(tmp_path), [str(child)], progress_callback=lambda *args: updates.append(args))
    assert updates == [(1, 1, 1, 0)]


# Отмена до старта сохраняет все папки.
def test_cancel_before_delete(tmp_path):
    child = tmp_path / 'empty'
    child.mkdir()
    stop = Event()
    stop.set()
    deleted, errors = delete_empty_folders(str(tmp_path), [str(child)], cancel_event=stop)
    assert not deleted and not errors and child.exists()


# Отмена после первого удаления сохраняет следующие папки.
def test_cancel_after_first(tmp_path):
    a = tmp_path / 'a'
    b = tmp_path / 'b'
    a.mkdir()
    b.mkdir()
    stop = Event()
    updates = []
    def report(*args):
        updates.append(args)
        stop.set()
    deleted, errors = delete_empty_folders(str(tmp_path), [str(a), str(b)], progress_callback=report, cancel_event=stop)
    assert len(deleted) == 1 and not errors and len(updates) == 1
    assert sum(p.exists() for p in (a, b)) == 1
