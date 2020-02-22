#!/usr/bin/env python

"""
Use local install for manual testing
"""

from devrepo import base_dir, shell

project_dir = base_dir()

shell("sudo python setup.py install")
