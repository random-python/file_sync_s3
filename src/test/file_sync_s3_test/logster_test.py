"""
"""

from file_sync_s3.logster import *

import time


@logster_duration
def module_function():
    time.sleep(0.25)


def test_logster():
    print()

    module_function()
