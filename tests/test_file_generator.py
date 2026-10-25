"""
Проверка создания файлов, их размера и содержимого,
перезаписи, прогресса, отмены и обработки ошибок.
"""
from threading import Event
from types import SimpleNamespace
import pytest
from file_generator import generate_file


# Нулевое содержимое и размер файла совпадают с параметрами.
def test_zero_file(tmp_path):
    path = generate_file(str(tmp_path), 'zeros.bin', 2, 'КБ', 'Нули')
    assert (tmp_path / 'zeros.bin').read_bytes() == bytes(2048)
    assert path == str(tmp_path / 'zeros.bin')


# Случайный файл имеет точный размер.
def test_random_file(tmp_path):
    generate_file(str(tmp_path), 'random.bin', 1, 'КБ', 'Случайные данные')
    assert (tmp_path / 'random.bin').stat().st_size == 1024


# Прогресс завершается полным числом записанных байтов.
def test_progress(tmp_path):
    updates = []
    generate_file(str(tmp_path), 'p.bin', 2, 'КБ', 'Нули', progress_callback=lambda done, total: updates.append((done, total)))
    assert updates[-1] == (2048, 2048)


# Без разрешения существующий файл сохраняется.
def test_existing_file_rejected(tmp_path):
    target = tmp_path / 'keep.bin'
    target.write_bytes(b'old')
    with pytest.raises(FileExistsError):
        generate_file(str(tmp_path), 'keep.bin', 1, 'КБ', 'Нули')
    assert target.read_bytes() == b'old'


# Разрешённая перезапись заменяет содержимое.
def test_overwrite(tmp_path):
    target = tmp_path / 'keep.bin'
    target.write_bytes(b'old')
    generate_file(str(tmp_path), 'keep.bin', 1, 'КБ', 'Нули', overwrite=True)
    assert target.read_bytes() == bytes(1024)


# Недостаток места выявляется до создания файла.
def test_no_disk_space(tmp_path, monkeypatch):
    monkeypatch.setattr('file_generator.shutil.disk_usage', lambda path: SimpleNamespace(free=0))
    with pytest.raises(OSError, match='Недостаточно'):
        generate_file(str(tmp_path), 'huge.bin', 1, 'КБ', 'Нули')
    assert not (tmp_path / 'huge.bin').exists()


# Неправильный размер отклоняется.
def test_invalid_size(tmp_path):
    with pytest.raises(ValueError):
        generate_file(str(tmp_path), 'bad.bin', 0, 'КБ', 'Нули')


# Несуществующий каталог отклоняется.
def test_missing_folder(tmp_path):
    with pytest.raises(ValueError):
        generate_file(str(tmp_path / 'missing'), 'a.bin', 1, 'КБ', 'Нули')


# Отмена очищает временный файл.
def test_cancel_cleanup(tmp_path):
    stop = Event()
    stop.set()
    with pytest.raises(InterruptedError):
        generate_file(str(tmp_path), 'cancel.bin', 1, 'КБ', 'Нули', cancel_event=stop)
    assert list(tmp_path.iterdir()) == []


# Отмена после первого блока не создаёт итоговый файл.
def test_cancel_after_progress(tmp_path):
    stop = Event()
    def report(done, total):
        stop.set()
    with pytest.raises(InterruptedError):
        generate_file(str(tmp_path), 'cancel.bin', 2, 'МБ', 'Нули', cancel_event=stop, progress_callback=report)
    assert list(tmp_path.iterdir()) == []
