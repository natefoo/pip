"""Generate and work with PEP 425 Compatibility Tags."""
from __future__ import absolute_import

import re
import sys
import string
import warnings
import platform

try:
    import sysconfig
except ImportError:  # pragma nocover
    # Python < 2.7
    import distutils.sysconfig as sysconfig
import distutils.util

from .platform import get_specific_platform


_osx_arch_pat = re.compile(r'(.+)_(\d+)_(\d+)_(.+)')


def normalize(s):
    """Remove all non-alphanumeric characters.
    """
    s = list(s.lower())
    for i, c in enumerate(s):
        s[i:i+1] = c if c in string.ascii_letters + string.digits else '_'
    return ''.join(s)


def get_abbr_impl():
    """Return abbreviated implementation name."""
    if hasattr(sys, 'pypy_version_info'):
        pyimpl = 'pp%s' % sys.version_info[0]
    elif sys.platform.startswith('java'):
        pyimpl = 'jy'
    elif sys.platform == 'cli':
        pyimpl = 'ip'
    else:
        pyimpl = 'cp'
    return pyimpl


def get_impl_ver():
    """Return implementation version."""
    if get_abbr_impl()[0:2] == 'pp':
        impl_ver = '%s%s' % (sys.pypy_version_info.major,
                             sys.pypy_version_info.minor)
    else:
        impl_ver = sysconfig.get_config_var("py_version_nodot")
        if not impl_ver:
                impl_ver = ''.join(map(str, sys.version_info[:2]))
    return impl_ver


def get_impl_ver_info():
    if get_abbr_impl()[0:2] == 'pp':
        return sys.pypy_version_info.major, sys.pypy_version_info.minor
    else:
        return sys.version_info[0], sys.version_info[1]


def get_abi_tag(default=None):
    soabi = sysconfig.get_config_var('SOABI')
    if not soabi:
        d = 'd' if hasattr(sys, 'pydebug') and sys.pydebug else ''
        u = 'u' if sys.maxunicode == 0x10ffff else ''
        abi = '%s%s%sm%s' % (get_abbr_impl(), get_impl_ver(), d, u)
    elif soabi.startswith('cpython-'):
        abi = 'cp' + soabi.split('-', 1)[-1]
    else:
        abi = default
    return abi


def get_platforms():
    """Return our platform name 'win32', 'linux_x86_64'"""
    # XXX remove distutils dependency
    platforms = ['any']
    plat = distutils.util.get_platform()
    platforms.append(normalize(plat))
    spec_plat = get_specific_platform()
    if spec_plat is not None:
        dist, major, full, stability = spec_plat
        major_version = normalize('-'.join([plat] + [dist, major]))
        full_version = normalize('-'.join([plat] + [dist, full]))
        platforms.append(major_version)
        if major_version != full_version:
            platforms.append(full_version)
    elif plat.startswith('linux'):
        platforms.append(normalize('-'.join([plat] + ['unknown_distribution',
                                                      'unknown_version'])))
    return list(reversed(platforms))


def get_platform():
    return get_platforms()[0]


def get_supported(versions=None, noarch=False):
    """Return a list of supported tags for each version specified in
    `versions`.

    :param versions: a list of string versions, of the form ["33", "32"],
        or None. The first version will be assumed to support our ABI.
    """
    supported = []

    # Versions must be given with respect to the preference
    if versions is None:
        versions = []
        version_info = get_impl_ver_info()
        major = version_info[0]
        # Support all previous minor Python versions.
        for minor in range(version_info[1], -1, -1):
            versions.append(''.join(map(str, (major, minor))))

    impl = get_abbr_impl()

    abis = []

    try:
        abi = get_abi_tag()
    except IOError as e:  # Issue #1074
        warnings.warn("{0}".format(e), RuntimeWarning)
        abi = None

    if abi:
        abis[0:0] = [abi]

    abi3s = set()
    import imp
    for suffix in imp.get_suffixes():
        if suffix[0].startswith('.abi'):
            abi3s.add(suffix[0].split('.', 2)[1])

    abis.extend(sorted(list(abi3s)))

    abis.append('none')

    if not noarch:
        platforms = get_platforms()
        arches = []
        for arch in platforms:
            if sys.platform == 'darwin':
                # support macosx-10.6-intel on macosx-10.9-x86_64
                match = _osx_arch_pat.match(arch)
                if match:
                    name, major, minor, actual_arch = match.groups()
                    actual_arches = [actual_arch]
                    if actual_arch in ('i386', 'ppc'):
                        actual_arches.append('fat')
                    if actual_arch in ('i386', 'x86_64'):
                        actual_arches.append('intel')
                    if actual_arch in ('i386', 'ppc', 'x86_64'):
                        actual_arches.append('fat3')
                    if actual_arch in ('ppc64', 'x86_64'):
                        actual_arches.append('fat64')
                    if actual_arch in ('i386', 'x86_64', 'intel', 'ppc', 'ppc64'):
                        actual_arches.append('universal')
                    tpl = '{0}_{1}_%i_%s'.format(name, major)
                    for m in range(int(minor) + 1):
                        for a in actual_arches:
                            arches.append(tpl % (m, a))
                else:
                    # arch pattern didn't match (?!)
                    arches.append(arch)
            else:
                arches.append(arch)

        # Current version, current API (built specifically for our Python):
        for abi in abis:
            for arch in arches:
                supported.append(('%s%s' % (impl, versions[0]), abi, arch))

        # Has binaries, does not use the Python API:
        supported.append(('py%s' % (versions[0][0]), 'none', arch))

    # No abi / arch, but requires our implementation:
    for i, version in enumerate(versions):
        supported.append(('%s%s' % (impl, version), 'none', 'any'))
        if i == 0:
            # Tagged specifically as being cross-version compatible
            # (with just the major version specified)
            supported.append(('%s%s' % (impl, versions[0][0]), 'none', 'any'))

    # No abi / arch, generic Python
    for i, version in enumerate(versions):
        supported.append(('py%s' % (version,), 'none', 'any'))
        if i == 0:
            supported.append(('py%s' % (version[0]), 'none', 'any'))

    return supported

supported_tags = get_supported()
supported_tags_noarch = get_supported(noarch=True)
