"""
Проверка управления файловыми операциями, их запуска,
отмены, обработки результатов, ошибок и журналирования.
"""
import threading
import time
import pytest
from operation_controller import OperationController


# Дожидаемся завершения рабочего потока, не используя фиксированные паузы.
def wait_for(controller, operation):
    method = {'scan': controller.poll_scan_updates, 'delete': controller.poll_delete_updates,
              'generation': controller.poll_generation_updates}[operation]
    collected = []
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        collected.extend(method())
        if any(kind in ('done', 'cancelled', 'error') for kind, _ in collected):
            return collected
        threading.Event().wait(0.005)
    pytest.fail('Фоновая операция не завершилась')


# Изначально очереди пусты, а отмена не запрошена.
def test_initial_state():
    controller = OperationController()
    assert controller.poll_scan_updates() == []
    assert controller.poll_delete_updates() == []
    assert controller.poll_generation_updates() == []
    assert not controller.scan_cancel_requested
    assert not controller.delete_cancel_requested


# Отмена переключает соответствующие события.
def test_cancel_events():
    controller = OperationController()
    controller.cancel_scan()
    controller.cancel_deletion()
    controller.cancel_generation()
    assert controller.scan_cancel_requested and controller.delete_cancel_requested
    assert controller._cancel['generation'].is_set()


# Проверка защищённых путей использует одну функцию для всего списка.
def test_system_paths(monkeypatch):
    monkeypatch.setattr('operation_controller.make_system_folder_checker', lambda: lambda path: path == 'protected')
    assert OperationController().get_system_paths(['ordinary', 'protected']) == ['protected']


# Выбор пользователя записывается в журнал.
@pytest.mark.parametrize('choice,expected', [
    ('deselect', 'Снято выделение'), ('continue', 'Пользователь разрешил')
])
def test_record_system_choice(monkeypatch, choice, expected):
    messages = []
    monkeypatch.setattr('operation_controller.log_operation', messages.append)
    OperationController().record_system_choice(choice)
    assert expected in messages[0]


# Успешный поиск передаёт результаты и не включает исходный каталог.
def test_scan_success(tmp_path, monkeypatch):
    child = tmp_path / 'empty'
    child.mkdir()
    def fake_scan(root, excluded, **kwargs):
        kwargs['progress_callback'](2)
        return [str(tmp_path), str(child)]
    monkeypatch.setattr('operation_controller.find_empty_folders', fake_scan)
    monkeypatch.setattr('operation_controller.log_operation', lambda message: None)
    messages = wait_after_start_scan(tmp_path)
    result = [value for kind, value in messages if kind == 'done'][0]
    assert result[0] == [str(child)] and result[3] == 2


def wait_after_start_scan(root):
    controller = OperationController()
    controller.start_scan(str(root))
    return wait_for(controller, 'scan')


# Сбой поиска передаётся интерфейсу сообщением об ошибке.
def test_scan_error(tmp_path, monkeypatch):
    errors = []
    monkeypatch.setattr('operation_controller.find_empty_folders', lambda *a, **k: (_ for _ in ()).throw(OSError('scan failed')))
    monkeypatch.setattr('operation_controller.log_error', errors.append)
    controller = OperationController()
    controller.start_scan(str(tmp_path))
    assert ('error', 'scan failed') in wait_for(controller, 'scan')
    assert errors


# Удаление передаёт итоги и фиксирует журнал.
def test_delete_success(tmp_path, monkeypatch):
    child = str(tmp_path / 'a')
    logs = []
    def fake_delete(root, selected, **kwargs):
        kwargs['progress_callback'](1, 1, 1, 0)
        return [child], []
    monkeypatch.setattr('operation_controller.delete_empty_folders', fake_delete)
    monkeypatch.setattr('operation_controller.log_operation', logs.append)
    controller = OperationController()
    controller.start_deletion(str(tmp_path), [child])
    messages = wait_for(controller, 'delete')
    assert any(kind == 'done' and value == ([child], [], 1, 1, False) for kind, value in messages)
    assert any('Удалена пустая папка' in line for line in logs)


# Контроллер фиксирует частичное удаление при отмене.
def test_delete_cancelled(tmp_path, monkeypatch):
    monkeypatch.setattr('operation_controller.log_operation', lambda message: None)
    def fake_delete(root, selected, **kwargs):
        kwargs['progress_callback'](1, 2, 1, 0)
        kwargs['cancel_event'].set()
        return [selected[0]], []
    monkeypatch.setattr('operation_controller.delete_empty_folders', fake_delete)
    controller = OperationController()
    controller.start_deletion(str(tmp_path), ['a', 'b'])
    messages = wait_for(controller, 'delete')
    assert any(kind == 'done' and value[-1] is True for kind, value in messages)


# Генерация возвращает путь и время выполнения.
def test_generation_success(tmp_path, monkeypatch):
    logs = []
    def fake_generation(folder, name, size, unit, kind, **kwargs):
        kwargs['progress_callback'](1024, 1024)
        return str(tmp_path / name)
    monkeypatch.setattr('operation_controller.generate_file', fake_generation)
    monkeypatch.setattr('operation_controller.log_operation', logs.append)
    controller = OperationController()
    controller.start_generation(str(tmp_path), 'x.bin', 1, 'КБ', 'Нули')
    messages = wait_for(controller, 'generation')
    assert any(kind == 'done' and value.endswith('x.bin') for kind, value in messages)
    assert any(kind == 'elapsed' and value >= 0 for kind, value in messages)
    assert any('время генерации' in line for line in logs)


# Генерация может завершиться отменой без итогового файла.
def test_generation_cancelled(tmp_path, monkeypatch):
    monkeypatch.setattr('operation_controller.generate_file', lambda *a, **k: (_ for _ in ()).throw(InterruptedError()))
    monkeypatch.setattr('operation_controller.log_operation', lambda message: None)
    controller = OperationController()
    controller.start_generation(str(tmp_path), 'x.bin', 1, 'КБ', 'Нули')
    assert ('cancelled', None) in wait_for(controller, 'generation')


# Второй поиск нельзя запустить, пока первый ещё работает.
def test_no_duplicate_scan(tmp_path, monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    def fake_scan(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return []
    monkeypatch.setattr('operation_controller.find_empty_folders', fake_scan)
    monkeypatch.setattr('operation_controller.log_operation', lambda message: None)
    controller = OperationController()
    try:
        controller.start_scan(str(tmp_path))
        assert entered.wait(2)
        with pytest.raises(RuntimeError):
            controller.start_scan(str(tmp_path))
    finally:
        release.set()
    assert any(kind == 'done' for kind, _ in wait_for(controller, 'scan'))
