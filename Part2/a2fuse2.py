# Name: Pranay Jhaveri
# Login: pjha607

from __future__ import print_function, absolute_import, division

import logging
import os
import sys
import errno

from collections import defaultdict
from fuse import FUSE, FuseOSError, Operations, LoggingMixIn
from passthrough import Passthrough
from errno import ENOENT
from stat import S_IFDIR, S_IFLNK, S_IFREG
from sys import argv, exit
from time import time

# Override Passthrough class for additional functionality
class A2Fuse2(LoggingMixIn, Passthrough):

    # Override "init" method for 2 root files (i.e. source1 & source2) and memory filesystem
    def __init__(self, root1, root2):
        self.root1 = root1
        self.root2 = root2
    
        self.files = {}
        self.data = defaultdict(bytes)
        self.fd = 0
        now = time()
        self.files['/'] = dict(st_mode=(S_IFDIR | 0o755), st_ctime=now,
                               st_mtime=now, st_atime=now, st_nlink=2)

    # Override "_full_path" method for return multiple source directories
    def _full_path(self, partial, myflag=False):

        if partial.startswith("/"):
            partial = partial[1:] 
        
        path = ""
        primarypath = ""
        if (myflag):
            primarypath = os.path.join(self.root2, partial)
        else:
            primarypath = os.path.join(self.root1, partial)


        if (myflag or os.path.exists(primarypath)):
            path = primarypath
        else:
            fallbackpath = os.path.join(self.root2, partial)
            if (os.path.exists(fallbackpath)):
                path = fallbackpath
            else:
                path = primarypath

        return path

    # Override "readdir" method so “ls” command in your mount can list the content 
    # of both source1 and source2
    def readdir(self, path, fh):
        
        full_path = self._full_path(path)
        dirents = ['.', '..']
        if os.path.isdir(full_path):
            dirents.extend(os.listdir(full_path))
        if self.root2 not in full_path:
            full_path = self._full_path(path, myflag=True)
        if os.path.isdir(full_path):
            dirents.extend(os.listdir(full_path))

    
        dirents.extend([x[1:] for x in self.files if x != '/'])
        for r in dirents:
            yield r

    # File methods that need to be overriden
    # ============
    def open(self, path, flags):
        if (path in self.files):
            self.fd = self.fd + 1
            return self.fd
        else:
            full_path = self._full_path(path)
            return os.open(full_path, flags)

    # Added st_uid and st_gid so the correct id is given for the new file that is being created
    # i.e. the gid and uid should not be "root"
    def create(self, path, mode, fi=None):
        self.files[path] = dict(st_mode=(S_IFREG | mode), st_nlink=1, st_uid=os.getuid(), st_gid=os.getgid(),
                                st_size=0, st_ctime=time(), st_mtime=time(),
                                st_atime=time())
        self.fd = self.fd + 1
        return self.fd

    def read(self, path, length, offset, fh):
    
        if (path in self.files):
            return self.data[path][offset:offset + length]
        else:
            os.lseek(fh, offset, os.SEEK_SET)
            return os.read(fh, length)

    def write(self, path, data, offset, fh):
        if (path in self.files):
            self.data[path] = self.data[path][:offset] + data
            self.files[path]['st_size'] = len(self.data[path])
            return len(data)
        else:
            os.lseek(fh, offset, os.SEEK_SET)
            return os.write(fh, data)
    
    def release(self, path, fh):
        if path not in self.files:
            return os.close(fh)

    def fsync(self, path, fdatasync, fh):
        if path not in self.files:
            return self.flush(path, fh)

    def flush(self, path, fh):
        if path not in self.files:
            return os.fsync(fh)
    
    
    # Filesystem methods that need to be overriden
    def getattr(self, path, fh=None):

        if (path in self.files):
            return self.files[path]
        else:
            full_path = self._full_path(path)
            st = os.lstat(full_path)
            return dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                                'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size', 'st_uid'))

    def unlink(self, path):
        if (path in self.files):
            self.files.pop(path)
        else:
            return os.unlink(self._full_path(path))

    def chmod(self, path, mode):
        if path not in self.files:
            full_path = self._full_path(path)
            return os.chmod(full_path, mode)
        else:
            self.files[path]['st_mode'] &= 0o770000
            self.files[path]['st_mode'] |= mode
            return 0

    # Override "truncate" method to add aditional data to file
    def truncate(self, path, length, fh=None):
        if (path not in self.files):
            full_path = self._full_path(path)
            with open(full_path, 'r+') as f:
                f.truncate(length)
        else:
            self.data[path] = self.data[path][:length]
            self.files[path]['st_size'] = length


    # Override access method so file can be removed from memory file system without asking beforehand
    def access(self, path, mode):
        if (path not in self.files):
            full_path = self._full_path(path)
            if not os.access(full_path, mode):
                raise FuseOSError(errno.EACCES)


# Main function for a2fuse2
def main(mountpoint, root1, root2):
    FUSE(A2Fuse2(root1, root2), mountpoint, nothreads=True, foreground=True)

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main(sys.argv[3], sys.argv[1], sys.argv[2])