#!/usr/bin/env python

"""
Squash github commits starting from a point
"""

from devrepo import shell

point = "61ea9c7353496c6f4c50acba37d511d32aaa354e"
message = "develop"

shell(f"git reset --soft {point}")
shell(f"git add --all")
shell(f"git commit --message='{message}'")
shell(f"git push --force --follow-tags")
