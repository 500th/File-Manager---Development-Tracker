import ntpath
import os


# Определение системных каталогов Windows для поиска и удаления.
def get_system_folders():
    drive = os.environ.get("SystemDrive", "C:")
    roots = [ntpath.join(drive + "\\", name) for name in (
        "Windows", "Windows.old", "Program Files", "Program Files (x86)", "ProgramData"
    )]
    for variable in ("SystemRoot", "windir", "ProgramFiles",
                     "ProgramFiles(x86)", "ProgramW6432", "ProgramData"):
        value = os.environ.get(variable)
        if value:
            roots.append(value)
    # AppData текущего пользователя и других профилей также содержит данные программ.
    for variable in ("APPDATA", "LOCALAPPDATA"):
        value = os.environ.get(variable)
        if value:
            roots.append(value)
    if os.name == "nt":
        profiles = ntpath.join(drive + "\\", "Users")
        try:
            with os.scandir(profiles) as entries:
                roots.extend(ntpath.join(entry.path, "AppData")
                             for entry in entries if entry.is_dir(follow_symlinks=False))
        except OSError:
            pass
    return roots


def normalize_path(path):
    if os.name == "nt":
        path = os.path.realpath(path)
    return ntpath.normcase(ntpath.abspath(path))


# Во время одного поиска корни вычисляются один раз, а не для каждой папки.
def make_system_folder_checker():
    roots = tuple({normalize_path(root) for root in get_system_folders()})

    def check(path):
        path = normalize_path(path)
        for root in roots:
            try:
                if ntpath.commonpath([path, root]) == root:
                    return True
            except ValueError:
                continue
        return False

    return check


def is_system_folder(path):
    return make_system_folder_checker()(path)
