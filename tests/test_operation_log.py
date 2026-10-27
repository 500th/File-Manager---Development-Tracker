"""
Проверка записи операций и ошибок в журнал,
а также правильности настройки логгера.
"""
import logging
import operation_log


# Информационное сообщение передаётся логгеру.
def test_info(caplog):
    with caplog.at_level(logging.INFO, logger='File_Manager_Utility'):
        operation_log.log_operation('test operation')
    assert any(record.message == 'test operation' and record.levelno == logging.INFO for record in caplog.records)


# Ошибка передаётся с уровнем ERROR.
def test_error(caplog):
    with caplog.at_level(logging.ERROR, logger='File_Manager_Utility'):
        operation_log.log_error('test error')
    assert any(record.message == 'test error' and record.levelno == logging.ERROR for record in caplog.records)


# Модуль использует отдельный логгер с поддержкой INFO.
def test_logger_configuration():
    assert operation_log.logger.name == 'File_Manager_Utility'
    assert operation_log.logger.isEnabledFor(logging.INFO)
