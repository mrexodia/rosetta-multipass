#!/usr/bin/env python

import os
import sys
import errno
import ctypes
import argparse
import logging
import stat

from fuse import FUSE, FuseOSError, Operations

# References:
# - https://github.com/libfuse/libfuse/blob/master/example/hello.c
# - https://github.com/fusepy/fusepy/blob/master/examples/memory.py
# - https://github.com/fusepy/fusepy/blob/master/examples/ioctl.py
# - https://threedots.ovh/blog/2022/06/quick-look-at-rosetta-on-linux/

class RosettaFS(Operations):
    log = logging.getLogger('RosettaFS')

    def __init__(self, rosetta_binary: str):
        # Virtualization check constants (https://threedots.ovh/blog/2022/06/quick-look-at-rosetta-on-linux/)
        self.ioctl_cmd = 0x80456122
        self.handshake = b"Our hard work\nby these words guarded\nplease don\'t steal\n\xc2\xa9 Apple Inc\0"

        # Load the contents of the original binary
        with open(rosetta_binary, "rb") as f:
            self.data = f.read()
        if self.handshake not in self.data:
            self.log.warning(f"Could not find handshake in binary. Either you are mounting the wrong binary or the virtualization check changed")

        # Proxy file attributes
        st = os.lstat(rosetta_binary)
        self.attr = dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                     'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))
        self.attr["st_mode"] = stat.S_IFREG | 0o755
        self.attr["st_nlink"] = 1

        self.log.info(f"Created mount, to test you can run: {rosetta_binary}. To register the binfmt handler:")
        self.log.info(f"sudo update-binfmts --install rosetta {rosetta_binary} --magic \"\\x7fELF\\x02\\x01\\x01\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x00\\x02\\x00\\x3e\\x00\" --mask \"\\xff\\xff\\xff\\xff\\xff\\xfe\\xfe\\x00\\xff\\xff\\xff\\xff\\xff\\xff\\xff\\xff\\xfe\\xff\\xff\\xff\" --credentials yes --preserve no --fix-binary no")

    def __call__(self, op, path, *args):
        def truncate(s):
            if len(s) > 256:
                return s[:256] + "..."
            return s

        self.log.debug('-> %s %s %s', op, path, truncate(repr(args)))

        ret = '[Unhandled Exception]'
        try:
            ret = getattr(self, op)(path, *args)
            return ret
        except OSError as e:
            ret = str(e)
            raise
        finally:
            self.log.debug('<- %s %s', op, truncate(repr(ret)))

    def readdir(self, path, fh):
        raise FuseOSError(errno.ENOTDIR)

    def getattr(self, path, fh=None):
        if path == "/":
            return self.attr
        raise FuseOSError(errno.ENOENT)

    def open(self, path, flags):
        if path == "/":
            return 1
        raise FuseOSError(errno.ENOENT)

    def read(self, path, size, offset, fh):
        if path == "/":
            return self.data[offset:offset + size]
        raise FuseOSError(errno.EIO)

    def ioctl(self, path, cmd, arg, fip, flags, data):
        if path == "/":
            if cmd == self.ioctl_cmd:
                self.log.debug(f"Handling rosetta handshake")
                ctypes.memmove(data, self.handshake, len(self.handshake))
                return 0
            else:
                self.log.error(f"Unsupported ioctl({hex(cmd)}) -> Probably the virtualization check changed")

        raise FuseOSError(errno.ENOTTY)

def main():
    parser = argparse.ArgumentParser("mount-rosetta")
    parser.add_argument("rosetta_binary", help="Path to the rosetta binary to mount")
    parser.add_argument('--debug', help="Enable debug logging", action=argparse.BooleanOptionalAction)
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    binary = args.rosetta_binary
    if not os.path.isfile(binary):
        raise FileNotFoundError(f"Rosetta binary not found: {binary}")
    FUSE(RosettaFS(binary), binary, nothreads=True, foreground=True, allow_other=True, nonempty=True)

if __name__ == "__main__":
    main()
