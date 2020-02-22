"""
usage example
"""

import os
import time
import shutil
import pathlib

from file_sync_s3_test import *

from file_sync_s3.watcher import *
from file_sync_s3.aws_s3 import AuthBucketS3, ConfigTransferS3

logger = logging.getLogger(__name__)

this_dir = os.path.dirname(os.path.abspath(__file__))
file_sync_dir = f"{this_dir}/tmp/file_sync"


def produce_name(index:int) -> str:
    return f"watcher-tester-{index}.binary"


def produce_path(file_name:str) -> str:
    return f"{file_sync_dir}/{file_name}"


def produce_file(file_name:str) -> None:
    file_path = produce_path(file_name)
    with open(file_path, "wb") as file_unit:
        file_unit.truncate(1 * 1024 * 1024)


def watcher_main():
    logger.info(f"INITIATE")

    shutil.rmtree(file_sync_dir, ignore_errors=True)
    os.makedirs(file_sync_dir)

    config_access = AuthBucketS3.default()
    config_transfer = ConfigTransferS3.default()

    bucket_operator = BucketOperatorS3(
        config_access=config_access,
        config_transfer=config_transfer,
    )

    folder_config = FolderConfig(
        folder_path=file_sync_dir,
        watcher_timeout=1,
        watcher_recursive=True,
        regex_include_list=[".+"],
        regex_exclude_list=[],
        keeper_expire=True,
        keeper_diem_span=3,
        keeper_scan_period=timedelta(seconds=3),
    )

    watcher_operator = WatcherOperator(
        bucket_operator=bucket_operator,
        folder_config=folder_config,
    )

    watcher_operator.initiate()

    for index in range(3):
        file_name = produce_name(index)
        produce_file(file_name)

    for index in range(3):
        file_name = produce_name(index)
        file_path = produce_path(file_name)
        pathlib.Path(file_path).touch()

    time.sleep(10)

    shutil.rmtree(file_sync_dir, ignore_errors=True)
    
    time.sleep(5)

    watcher_operator.terminate()

    logger.info(f"TERMINATE")


if __name__ == "__main__":
    watcher_main()
