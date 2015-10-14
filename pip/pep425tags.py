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


def get_config_var(var):
    try:
        return sysconfig.get_config_var(var)
    except IOError as e:  # Issue #1074
        warnings.warn("{0}".format(e), RuntimeWarning)
        return None


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
    impl_ver = get_config_var("py_version_nodot")
    if not impl_ver or get_abbr_impl() == 'pp':
        impl_ver = ''.join(map(str, get_impl_version_info()))
    return impl_ver


def get_impl_version_info():
    """Return sys.version_info-like tuple for use in decrementing the minor
    version."""
    if get_abbr_impl() == 'pp':
        # as per https://github.com/pypa/pip/issues/2882
        return (sys.version_info[0], sys.pypy_version_info.major,
                sys.pypy_version_info.minor)
    else:
        return sys.version_info[0], sys.version_info[1]


def get_flag(var, fallback, expected=True, warn=True):
    """Use a fallback method for determining SOABI flags if the needed config
    var is unset or unavailable."""
    val = get_config_var(var)
    if val is None:
        if warn:
            warnings.warn("Config variable '{0}' is unset, Python ABI tag may "
                          "be incorrect".format(var), RuntimeWarning, 2)
        return fallback()
    return val == expected


def get_abi_tag():
    """Return the ABI tag based on SOABI (if available) or emulate SOABI
    (CPython 2, PyPy)."""
    soabi = get_config_var('SOABI')
    impl = get_abbr_impl()
    if not soabi and impl in ('cp', 'pp') and hasattr(sys, 'maxunicode'):
        d = ''
        m = ''
        u = ''
        if get_flag('Py_DEBUG',
                    lambda: hasattr(sys, 'gettotalrefcount'),
                    warn=(impl == 'cp')):
            d = 'd'
        if get_flag('WITH_PYMALLOC',
                    lambda: impl == 'cp',
                    warn=(impl == 'cp')):
            m = 'm'
        if get_flag('Py_UNICODE_SIZE',
                    lambda: sys.maxunicode == 0x10ffff,
                    expected=4,
                    warn=(impl == 'cp' and
                          sys.version_info < (3, 3))) \
                and sys.version_info < (3, 3):
            u = 'u'
        abi = '%s%s%s%s%s' % (impl, get_impl_ver(), d, m, u)
    elif soabi and soabi.startswith('cpython-'):
        abi = 'cp' + soabi.split('-')[1]
    elif soabi:
        abi = soabi.replace('.', '_').replace('-', '_')
    else:
        abi = None
    return abi


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
        version_info = get_impl_version_info()
        major = version_info[:-1]
        # Support all previous minor Python versions.
        for minor in range(version_info[-1], -1, -1):
            versions.append(''.join(map(str, major + (minor,))))

    impl = get_abbr_impl()

    abis = []

    abi = get_abi_tag()
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
                    for m in reversed(range(int(minor) + 1)):
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
