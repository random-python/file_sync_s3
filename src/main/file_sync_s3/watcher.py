"""
file watch support
"""

import re
import os
import time
import logging

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Callable

from watchdog.events import FileSystemEvent, FileModifiedEvent
from watchdog.events import EVENT_TYPE_CREATED
from watchdog.events import EVENT_TYPE_MODIFIED
from watchdog.events import EVENT_TYPE_DELETED
from watchdog.events import EVENT_TYPE_MOVED
from watchdog.events import RegexMatchingEventHandler
from watchdog.observers import Observer
from watchdog.utils import BaseThread

from file_sync_s3.config import CONFIG
from file_sync_s3.aws_s3 import BucketOperatorS3, SupportFuncS3

logger = logging.getLogger(__name__)

frozen = dataclass(frozen=True)

override = lambda function : function


@frozen
class FolderConfig:
    "sync folder params"

    config_entry = "folder/watcher"

    folder_path:str
    watcher_timeout:int
    watcher_recursive:bool
    regex_include_list:List[str]
    regex_exclude_list:List[str]
    keeper_expire:bool
    keeper_diem_span:int
    keeper_scan_period:timedelta

    @classmethod
    def default(cls) -> "FolderConfig":
        ""
        section = CONFIG[cls.config_entry]
        return FolderConfig(
            folder_path=section['folder_path'],
            watcher_timeout=section['watcher_timeout@int'],
            watcher_recursive=section['watcher_recursive@bool'],
            regex_include_list=section['regex_include@list'],
            regex_exclude_list=section['regex_exclude@list'],
            keeper_expire=section['keeper_expire@bool'],
            keeper_diem_span=section['keeper_diem_span@int'],
            keeper_scan_period=section['keeper_scan_period@timedelta'],
        )


class FolderVisitor:
    "file system tree walker with regex matcher"

    def __init__(self,
            folder_config:FolderConfig=None,
        ):
        self.folder_config = folder_config or FolderConfig.default()
        self.regex_include_list = [re.compile(regex) for regex in self.folder_config.regex_include_list]
        self.regex_exclude_list = [re.compile(regex) for regex in self.folder_config.regex_exclude_list]

    def visit_store(self, visit_action:Callable) -> None:
        "apply action to local storage"
        folder_root = self.folder_config.folder_path
        for base, dir_list, file_list in os.walk(folder_root):
            for file in file_list:
                file_path = f"{base}/{file}"
                visit_action(file_path)

    def has_regex_match(self, file_path:str) -> bool:
        "match file path against configured patterns"
        if not os.path.isfile(file_path):
            return False
        if any(regex.match(file_path) for regex in self.regex_exclude_list):
            return False
        if any(regex.match(file_path) for regex in self.regex_include_list):
            return True
        return False


class FolderKeeper(BaseThread, FolderVisitor):
    "file expiration managaer"

    def __init__(self,
            folder_config:FolderConfig=None,
        ):
        BaseThread.__init__(self)
        FolderVisitor.__init__(self, folder_config)

    @override
    def run(self) -> None:
        while self.should_keep_running():
            logger.info(f"process expirations")
            try:
                self.visit_store(self.perform_expire)
            except Exception as error:
                logger.error(f"failure: {error}")
            time.sleep(self.folder_config.keeper_scan_period.total_seconds())

    def perform_expire(self, file_path:str) -> None:
        "expire matching local file"
        if not self.has_regex_match(file_path):
            logger.info(f"no match: {file_path}")
            return
        current = datetime.now().astimezone(timezone.utc)
        modified = SupportFuncS3.convert_unix_time(os.path.getmtime(file_path))
        delta_time = current - modified
        delta_days = delta_time.days
        if  delta_days >= self.folder_config.keeper_diem_span:
            logger.info(f"expire: {file_path} delta_days={delta_days}")
            os.remove(file_path)
        else:
            logger.info(f"retain: {file_path} delta_days={delta_days}")


@frozen
class EventEntry:
    "postponed file event"

    stamp:float  # event fire time
    event:FileSystemEvent  # original event


class EventReactor(BaseThread, FolderVisitor, RegexMatchingEventHandler):
    "file watch change event handler"

    def __init__(self,
            folder_config:FolderConfig=None,
            bucket_operator:BucketOperatorS3=None,
        ):
        self.event_dict = dict()
        self.folder_config = folder_config or FolderConfig.default()
        self.bucket_operator = bucket_operator or BucketOperatorS3()
        BaseThread.__init__(self)
        FolderVisitor.__init__(self,
            self.folder_config,
        )
        RegexMatchingEventHandler.__init__(self,
            ignore_directories=True,
            regexes=self.folder_config.regex_include_list,
            ignore_regexes=self.folder_config.regex_exclude_list,
         )

    @override
    def on_any_event(self, event:FileSystemEvent) -> None:
        "postpone event processing to settle file changes"
        self.event_dict[event.src_path] = EventEntry(
            stamp=time.time(),
            event=event,
        )

    @override
    def run(self) -> None:
        "periodic verification for settled file changes"
        self.populate_init()
        while self.should_keep_running():
            try:
                self.perform_expire()
            except Exception as error:
                logger.error(f"failure: {error}")
            time.sleep(1)

    def populate_init(self) -> None:
        logger.info("sync initial state")
        self.visit_store(self.perform_register)

    def perform_register(self, file_path:str) -> None:
        if self.has_regex_match(file_path):
            event = FileModifiedEvent(file_path)
            self.on_any_event(event)

    def perform_expire(self) -> None:
        "check for settled file changes after a timeout"
        if not self.event_dict:
            return
        current = time.time()
        timeout = self.folder_config.watcher_timeout
        for file_path in list(self.event_dict.keys()):
            event_entry = self.event_dict[file_path]
            if event_entry.stamp + timeout < current:
                del self.event_dict[file_path]
                self.process_event(event_entry.event)

    def process_event(self, event:FileSystemEvent) -> None:
        "apply pending file change event"
        event_type = event.event_type
        local_path = event.src_path
        remot_path = os.path.relpath(local_path, self.folder_config.folder_path)
        if event_type == EVENT_TYPE_CREATED:
            self.bucket_operator.resource_put_sync(local_path, remot_path)
        elif event_type == EVENT_TYPE_MODIFIED:
            self.bucket_operator.resource_put_sync(local_path, remot_path)
        elif event_type == EVENT_TYPE_DELETED:
            self.bucket_operator.resource_delete_sync(remot_path)
        elif event_type == EVENT_TYPE_MOVED:
            self.bucket_operator.resource_delete_sync(remot_path)
            local_path = event.dest_path
            remot_path = os.path.relpath(local_path, self.folder_config.folder_path)
            self.bucket_operator.resource_put_sync(local_path, remot_path)
        else:
            logger.error(f"no event type: {event_type}")


class WatcherOperator:
    "file watch manager"

    def __init__(self,
            folder_config:FolderConfig=None,
            folder_keeper:FolderKeeper=None,
            bucket_operator:BucketOperatorS3=None,
        ) -> None:
        ""
        self.folder_config = folder_config or FolderConfig.default()
        self.folder_keeper = folder_keeper or FolderKeeper(self.folder_config)
        self.bucket_operator = bucket_operator or BucketOperatorS3()
        self.event_reactor = EventReactor(
            folder_config=folder_config,
            bucket_operator=bucket_operator,
        )
        self.folder_observer = Observer(
            timeout=self.folder_config.watcher_timeout,
        )
        self.folder_observer.schedule(
            event_handler=self.event_reactor,
            path=self.folder_config.folder_path,
            recursive=self.folder_config.watcher_recursive,
        )

    def initiate(self) -> None:
        logger.info("start service threads")
        self.event_reactor.start()
        self.folder_keeper.start()
        self.folder_observer.start()

    def terminate(self) -> None:
        logger.info("stop service threads")
        self.folder_observer.stop()
        self.folder_keeper.stop()
        self.event_reactor.stop()
