"""
logging support
"""

import functools
import inspect
import logging
import time

from typing import Awaitable
from typing import Callable
from typing import Union

logger = logging.getLogger(__name__)

UNI_TYPE = Union[Awaitable, Callable]


def logster_duration(function:UNI_TYPE) -> UNI_TYPE:
    "report function duration"

    def report_duration(time_start, time_finish):
        time_diff = time_finish - time_start
        logger.info(f"{function.__name__}: {time_diff}")

    if inspect.iscoroutinefunction(function):

        async def decorator(*args, **kwargs) -> object:
            try:
                time_start = time.time()
                return await function(*args, **kwargs)
            finally:
                time_finish = time.time()
                report_duration(time_start, time_finish)

    else:

        def decorator(*args, **kwargs) -> object:
            try:
                time_start = time.time()
                return function(*args, **kwargs)
            finally:
                time_finish = time.time()
                report_duration(time_start, time_finish)

    return functools.wraps(function)(decorator)
