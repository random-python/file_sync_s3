"""
"""

from file_sync_s3.setup import *

this_dir = os.path.dirname(os.path.abspath(__file__))

os.environ['FILE_SYNC_ROOT_DIR'] = f"{this_dir}"

def test_setup():
    print()
