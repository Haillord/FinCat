import subprocess
import hashlib
import platform

def get_hwid():
    """
    Возвращает стабильный идентификатор устройства на основе серийного номера системного диска.
    Если не удаётся, использует комбинацию имени компьютера и объёма диска C:.
    """
    system = platform.system()
    if system == 'Windows':
        return _get_windows_hwid()
    else:
        # Для других ОС можно добавить позже
        return _get_fallback_hwid()

def _get_windows_hwid():
    # Попытка через WMIC (основной метод)
    try:
        output = subprocess.check_output(
            ['wmic', 'diskdrive', 'where', 'index=0', 'get', 'serialnumber'],
            stderr=subprocess.DEVNULL,
            text=True
        )
        lines = [line.strip() for line in output.splitlines() if line.strip() and 'serialnumber' not in line.lower()]
        if lines:
            serial = lines[0]
            return hashlib.md5(serial.encode('utf-8')).hexdigest()
    except Exception:
        pass

    # Fallback: серийный номер тома C:
    try:
        import win32api
        volume_info = win32api.GetVolumeInformation("C:\\")
        serial = str(volume_info[1])  # серийный номер тома
        return hashlib.md5(serial.encode('utf-8')).hexdigest()
    except ImportError:
        # win32api может отсутствовать
        pass
    except Exception:
        pass

    # Последний fallback: комбинация hostname и размера диска
    return _get_fallback_hwid()

def _get_fallback_hwid():
    import socket
    import shutil
    host = socket.gethostname()
    total, used, free = shutil.disk_usage("C:\\")
    raw = f"{host}-{total}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()