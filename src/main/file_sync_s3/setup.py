"""
system service support
"""

import os
import shutil
from typing import List


def root_dir() -> str:
    return os.environ.get('FILE_SYNC_ROOT_DIR', "/")


def initd_list() -> List[str]:
    return [
        f"/etc/init.d/file_sync_s3",
    ]


def systemd_list() -> List[str]:
    return [
        f"/etc/systemd/system/file_sync_s3.service",
    ]


def has_initd() -> bool:
    return shutil.which("systemctl") is None


def service_list() -> List[str]:
    ""
    if has_initd():
        return initd_list()
    else:
        return systemd_list()


def service_enable(service:str) -> None:
    ""
    service = os.path.basename(service)
    if has_initd():
        rc_update = shutil.which("rc-update")
        command = f"{rc_update} add {service}"
    else:
        systemctl = shutil.which("systemctl")
        command = f"{systemctl} enable {service}"
    os.system(command)


def service_disable(service:str) -> None:
    ""
    service = os.path.basename(service)
    if has_initd():
        rc_update = shutil.which("rc-update")
        command = f"{rc_update} del {service}"
    else:
        systemctl = shutil.which("systemctl")
        command = f"{systemctl} disable {service}"
    os.system(command)


def service_install():
    ""
    this_dir = os.path.dirname(os.path.abspath(__file__))
    for service in service_list():
        source = f"{this_dir}{service}"
        target = f"{root_dir()}{service}"
        parent = os.path.dirname(target)
        os.makedirs(parent, mode=0o755, exist_ok=True)
        shutil.copy(source, target)
        service_enable(service)


def service_uninstall():
    ""
    for service in service_list():
        target = f"{root_dir()}{service}"
        if os.path.exists(target):
            service_disable(service)
            os.remove(target)
