"""
Проверка поиска пустых папок, работы исключений и защиты
системных каталогов, отмены поиска и обработки ошибок.
"""
import os
from threading import Event

import pytest

import folder_scanner
from folder_scanner import find_empty_folders


# Отключает защиту системных путей только для обычных тестовых каталогов.
# Проверки самой защиты ниже переопределяют эту подмену отдельно.
@pytest.fixture(autouse=True)
def allow_test_directories(monkeypatch):
    monkeypatch.setattr(
        "folder_scanner.make_system_folder_checker",
        lambda: lambda path: False
    )


# Пустой вложенный каталог должен присутствовать в результате.
def test_empty_child_found(tmp_path):
    child = tmp_path / 'empty'
    child.mkdir()
    assert str(child) in find_empty_folders(str(tmp_path))


# Каталог с файлом не считается пустым.
def test_nonempty_child_not_found(tmp_path):
    child = tmp_path / 'nonempty'
    child.mkdir()
    (child / 'keep.txt').write_text('data', encoding='utf-8')
    assert str(child) not in find_empty_folders(str(tmp_path))


# Пустыми признаются и дочерняя, и родительская вложенные папки.
def test_nested_empty_folders(tmp_path):
    parent = tmp_path / 'parent'
    leaf = parent / 'leaf'
    leaf.mkdir(parents=True)
    found = find_empty_folders(str(tmp_path))
    assert str(parent) in found
    assert str(leaf) in found


# Исключённая ветвь не обходится; её родитель не становится ложно пустым.
def test_exclusion_prunes_branch(tmp_path):
    excluded = tmp_path / 'excluded'
    excluded.mkdir()
    result = find_empty_folders(str(tmp_path), excluded_paths=[str(excluded)])
    assert str(excluded) not in result
    assert str(tmp_path) not in result


# Для защищённого корня поиск не начинается.
def test_system_root_skipped_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr("folder_scanner.make_system_folder_checker", lambda: lambda path: True)
    assert find_empty_folders(str(tmp_path)) == []


# Системная ветвь пропускается по умолчанию и включается по флажку.
def test_system_branch_skipped_and_included(tmp_path, monkeypatch):
    system_branch = tmp_path / 'protected'
    system_branch.mkdir()
    monkeypatch.setattr(
        "folder_scanner.make_system_folder_checker",
        lambda: lambda path: os.path.normcase(os.path.abspath(path)) == os.path.normcase(
            os.path.abspath(system_branch)),
    )
    assert str(system_branch) not in find_empty_folders(str(tmp_path))
    assert str(system_branch) in find_empty_folders(str(tmp_path), include_system=True)


# Счётчик получает последовательное число просмотренных каталогов.
def test_progress_counts_visited_directories(tmp_path):
    (tmp_path / 'one').mkdir()
    (tmp_path / 'two').mkdir()
    progress = []
    find_empty_folders(str(tmp_path), progress_callback=progress.append)
    assert progress == [1, 2, 3]


# Установленный Event прерывает поиск.
def test_cancel_before_scan(tmp_path):
    event = Event()
    event.set()
    with pytest.raises(InterruptedError):
        find_empty_folders(str(tmp_path), cancel_event=event)


# Отмена обрабатывается также на обратном проходе.
def test_cancel_during_reverse_pass(tmp_path):
    event = Event()

    def cancel_after_first(count):
        event.set()

    with pytest.raises(InterruptedError):
        find_empty_folders(str(tmp_path), progress_callback=cancel_after_first, cancel_event=event)


# При ошибке доступа ветвь пропускается, а родитель не считается пустым.
def test_permission_error_saved_and_parent_not_empty(tmp_path, monkeypatch):
    denied = tmp_path / 'denied'
    error = PermissionError(13, 'Access denied', str(denied))

    def fake_walk(root, topdown=True, onerror=None):
        yield str(tmp_path), ['denied'], []
        onerror(error)

    monkeypatch.setattr(folder_scanner.os, 'walk', fake_walk)
    skipped = []
    result = find_empty_folders(str(tmp_path), skipped_errors=skipped)
    assert result == []
    assert skipped == [error]


# Ошибки, отличные от PermissionError, не скрываются.
def test_other_walk_error_propagates(tmp_path, monkeypatch):
    def fake_walk(root, topdown=True, onerror=None):
        onerror(OSError('Disk error'))
        yield str(tmp_path), [], []

    monkeypatch.setattr(folder_scanner.os, 'walk', fake_walk)
    with pytest.raises(OSError, match='Disk error'):
        find_empty_folders(str(tmp_path))
