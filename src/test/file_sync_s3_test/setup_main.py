"""
"""

from file_sync_s3.setup import *

this_dir = os.path.dirname(os.path.abspath(__file__))

os.environ['FILE_SYNC_ROOT_DIR'] = f"{this_dir}"

def setup_main():
    print()
    
    service_install()

    service_uninstall()

if __name__ == "__main__":
    setup_main()
