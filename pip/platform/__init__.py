"""Add additional specificity to the platform portion of PEP 425 tags"""

import distutils.util

from . import linux


def get_specific_platform():
    base = distutils.util.get_platform().split('-')[0]
    if base == 'linux':
        return linux.get_specific_platform()
    return None
