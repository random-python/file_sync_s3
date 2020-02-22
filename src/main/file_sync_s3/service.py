"""
service invocation
"""

import os
import signal
import logging
import threading

from file_sync_s3.watcher import WatcherOperator


def setup_logger() -> None:

    console_date_format = "%Y-%m-%d %H:%M:%S"
    console_record_format = "%(asctime)s %(levelname)-.4s %(name)12s:%(lineno)03d  %(funcName)-22s  %(message)s"

    logging.basicConfig(
        level=logging.INFO,
        datefmt=console_date_format,
        format=console_record_format,
    )


def service_main() -> int:
    "service invocation"

    setup_logger()

    watcher_operator = WatcherOperator()

    signum_list = [
        signal.SIGHUP,
        signal.SIGINT,
        signal.SIGTERM,
        signal.SIGUSR1,
        signal.SIGUSR2,
    ]

    signal_event = threading.Event()

    def signal_reactor(signum, frame) -> None:
        signal_event.set()

    for signum in signum_list:
        signal.signal(signum, signal_reactor)

    watcher_operator.initiate()

    signal_event.wait()

    watcher_operator.terminate()

    return 0
