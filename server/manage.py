#!/usr/bin/env python
# SPDX-License-Identifier: LicenseRef-CloudHub-Commercial
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloud_accounts.settings')
from django.core.management import execute_from_command_line

execute_from_command_line(sys.argv)
