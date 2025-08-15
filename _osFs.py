#!/usr/bin/env
# -*- coding: utf-8 -*-
"""
ezFS access into the current filesystem
"""
import typing
from abc import abstractmethod
import os
import shutil
from paths import asUrl, UrlCompatible, URL
import ezFs


class OsItem(ezFs.EzFsItem):
    """
    A single item on the os filesystem tree
    """

    def __init__(self,url:UrlCompatible,filesystem:"OsFs"):
        ezFs.EzFsItem.__init__(self,url,filesystem)
        self.canWatch:bool=True

    @property
    @abstractmethod
    def isDir(self)->bool:
        """ is this a directory? """
        # NOTE: don't "need to" put this here, but pylint
        # needs at least one abstract method to treat the class
        # as abstract.

    def removeWatch(self,
        watchFn:ezFs.WatcherFn
        )->None:
        """
        Quit watching an item for changes.

        :param watchFn: _description_
        :type watchFn: ezFs.WatcherFn
        :return: _description_
        :rtype: _type_
        """
        # TODO: implement removeWatch
        _=watchFn
        raise NotImplementedError()

    def addWatch(self,watchFn:ezFs.WatcherFn,pollingInterval:float=30):
        """
        When the file or directory changes, will call a watchFn(file,operation)
        where operation can be one of "CREATE,UPDATE,DELETE,RENAME"

        This call returns immediately.
        The return value is a running thread or None if there was nothing to watch.

        See also:
            http://timgolden.me.uk/python/win32_how_do_i/watch_directory_for_changes.html
        """
        source=self.abspath
        if os.name=='nt': # windows
            import win32con
            import win32file
            ACTIONS = {
                1 : "CREATE",
                2 : "DELETE",
                3 : "UPDATE",
                4 : "CREATE", # actually renamed in from somewhere else
                5 : "RENAME"
            }
            FILE_LIST_DIRECTORY = 0x0001
            hDir = win32file.CreateFile ( # pylint: disable=c-extension-no-member
                source,
                FILE_LIST_DIRECTORY,
                win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
                None,
                win32con.OPEN_EXISTING,
                win32con.FILE_FLAG_BACKUP_SEMANTICS,
                None
            )
            while True:
                #
                # ReadDirectoryChangesW takes a previously-created
                # handle to a directory, a buffer size for results,
                # a flag to indicate whether to watch subtrees and
                # a filter of what changes to notify.
                #
                # NB Tim Juchcinski reports that he needed to up
                # the buffer size to be sure of picking up all
                # events when a large number of files were
                # deleted at once.
                #
                results = win32file.ReadDirectoryChangesW ( # pylint: disable=c-extension-no-member
                    hDir,
                    1024,
                    True,
                    win32con.FILE_NOTIFY_CHANGE_FILE_NAME |
                        win32con.FILE_NOTIFY_CHANGE_DIR_NAME |
                        win32con.FILE_NOTIFY_CHANGE_ATTRIBUTES |
                        win32con.FILE_NOTIFY_CHANGE_SIZE |
                        win32con.FILE_NOTIFY_CHANGE_LAST_WRITE |
                        win32con.FILE_NOTIFY_CHANGE_SECURITY,
                    None,
                    None
                )
                for action,filename in results:
                    full_filename=os.path.join(source,filename)
                    try:
                        watchFn(full_filename,ACTIONS[action])
                    except Exception as e: # pylint: disable=broad-except
                        # cannot have this throw or it would prevent others executing
                        print(e)
        elif os.name=='posix': # linux-like system
            # TODO: Works for directory, not file
            import time
            import signal
            def handler(signum,frame):
                """
                event handler for linux filesystem
                """
                _=signum,frame
                watchFn(source,'UPDATE')
            if hasattr(signal,'SIGIO'):
                signal.signal(signal.SIGIO,handler)
            else:
                print('WARN: unable to import signal.SIGIO')
            f=os.open(source,os.O_RDONLY)
            try:
                import fcntl
                fcntl.fcntl(f,fcntl.F_SETSIG,0)
                fcntl.fcntl(f,fcntl.F_NOTIFY,fcntl.DN_MODIFY|fcntl.DN_CREATE|fcntl.DN_MULTISHOT)
            except ImportError:
                print('WARN: unable to import fcntl')
            while True:
                time.sleep(pollingInterval*1000)
        else: # in case all else fails, try polling on it
            # poll using standard io (TODO: do as thread)
            if not self.isDir:
                lastchange=os.stat(source).st_mtime
                while True:
                    time.sleep(pollingInterval*1000)
                    try:
                        if os.stat(source).st_mtime!=lastchange:
                            lastchange=os.stat(source).st_mtime
                            watchFn(source,'UPDATE')
                    except Exception as e: # pylint: disable=broad-except
                        # cannot have user-supplied function throw
                        print(e)
                        watchFn(source,'DELETE')
            else:
                import time
                before=dict([(f, None) for f in os.listdir(source)])
                while True:
                    time.sleep(pollingInterval*1000)
                    after=dict([(f, None) for f in os.listdir(source)])
                    added=[f for f in after if f not in before]
                    removed=[f for f in before if f not in after]
                    for filename in added:
                        watchFn(source,'CREATE')
                    if removed:
                        watchFn(source,'REMOVE')
                    #TODO: account for changes
                    before=after


class OsFile(ezFs.EzFsFile,OsItem):
    """
    File on the current operating system.

    This can be used directly as a file-like object.
    """

    def __init__(self,url:UrlCompatible,filesystem:"OsFs"):
        ezFs.EzFsFile.__init__(self,url,filesystem)
        OsItem.__init__(self,url,filesystem)
        self._f:typing.Optional[typing.IO]=None

    def open(self,fileAccessMode:typing.Optional[str]=None)->"OsFile":
        """
        returns an actual file object rather than just a file-like object

        for simple operations like only reading or only writing, no
        need to call this explicitly.  It will be called on demand!
        """
        if self._f is None:
            if self.url is None or self.url.filePath is None:
                raise Exception("Null file location")
            self.isOpen=True
            if fileAccessMode is None:
                fileAccessMode=self._fileAccessMode
            else:
                self._fileAccessMode:str=fileAccessMode
            self._f=open(self.url.filePath,fileAccessMode,encoding='utf-8')
        else:
            self.seek(0)
        return self

    def __del__(self)->None:
        """
        Attempt to auto-close when object is deleted
        """
        self.close()

    def seek(self,offset:int,whence:int=0)->None:
        """
        jump to file position
        """
        if self._f is None:
            if offset==0 and whence==0:
                # whenever we do open we'll be at the beginning
                return
            self.open()
        self._f.seek(offset,whence) # type: ignore

    def tell(self)->int:
        """
        get the current file position
        """
        if self._f is None:
            # whenever we do open we'll be at the beginning
            return 0
        return self._f.tell()

    def read(self,
        numBytes:typing.Optional[int]=None,
        encoding:str=None
        )->str:
        """
        read n# of bytes, or the whole thing
        """
        if self._f is None:
            self._f=self.open('rb')
        data=self._f.read(numBytes)
        if encoding is not None:
            data=data.decode(encoding)
        return data

    def write(self,data:typing.Any,encoding:str='utf-8')->int:
        """
        Write the data to the file
        """
        if self._f is None:
            self.open('wb')
        if not isinstance(data,bytes):
            if not isinstance(data,str):
                data=str(data)
            data=data.encode(encoding)
        return self._f.write(data)  # type: ignore

    def close(self)->None:
        """
        Close the underlying file
        """
        if self._f is not None:
            self.isOpen=False
            self.fileAccessMode=''
            self._f.close()
            self._f=None

    def flush(self)->None:
        """
        Complete all i/o operations
        """
        if self._f is None:
            raise Exception("File not open")
        self._f.flush()


class OsDirectory(ezFs.EzFsDirectory,OsItem):
    """
    Represents a directory on the current operating system
    """

    def __init__(self,url:UrlCompatible,filesystem:"OsFs"):
        ezFs.EzFsDirectory.__init__(self,url,filesystem)
        OsItem.__init__(self,url,filesystem)
        self._children:typing.Optional[OsItem]=None

    def markDirty(self)->None:
        """
        mark the underlying dataset as having changed
        """
        self._children=None

    @property
    def children(self)->typing.Iterable[OsItem]:
        """
        get all of the files in this directory
        """
        if self._children is None:
            self._children=self.filesystem._dir(self) # pylint: disable=protected-access
        return self._children

    def mount(self,
        location: UrlCompatible,
        otherFs: typing.Optional["ezFs.EzFsFilesystem"] = None
        ) -> URL:
        # TODO: what does this mean for this type?
        _=location,otherFs
        raise NotImplementedError()


class OsFs(ezFs.EzFsFilesystem,OsDirectory):
    """
    The current OS's (disk) filesystem
    """

    URL_PROTOCOLS=['file://','',None]

    def __init__(self,url:UrlCompatible=None,defaultLocationCwd:bool=True):
        caseSensitive=(os.sep!='\\')
        if url is None or (isinstance(url,str) and not url): # if None or empty string
            if defaultLocationCwd:
                url=asUrl(os.getcwd())
            else:
                if os.name=='nt':
                    url=asUrl('c:\\')
                else:
                    url=asUrl('/')
        else:
            url=asUrl(url)
        ezFs.EzFsFilesystem.__init__(self,url,caseSensitive)
        OsDirectory.__init__(self,url,self)

    @property
    def root(self):
        d=OsDirectory('file://',self)
        return d

    def _getFsItem(self,url:UrlCompatible)->OsItem:
        """
        get a single item based upon location
        """
        url=asUrl(url)
        path=url.filePath
        if not path:
            path=os.curdir
        if os.path.isdir(path):
            item=OsDirectory(url,self)
        elif os.path.exists(path):
            item=OsFile(url,self)
        else:
            raise ezFs.NoFileException(path)
        return item

    def read(self,
        locationString:UrlCompatible,
        justOne:bool=True,
        recursive:bool=False,
        printErrors:bool=True):
        """
        shortcut to easily read files
        """
        if locationString.startswith('file://'):
            locationString=locationString[7:]
            split=locationString.split('/')
            sysLocation=os.sep.join(split)
        else:
            split=locationString.split(os.sep)
            sysLocation=locationString
        if locationString in ('_','stdin'):
            return None # TODO: need to pass this up into the formats bin and
            #           read whatever is on standard input
        if os.path.isfile(sysLocation):
            return None # TODO: need to pass this up into the formats bin to read
        if os.path.isdir(sysLocation):
            return None # TODO: read all the files in this directory... and possibly subdirectories
        currentPath=split[0]
        for level in split[1:]:
            if os.path.isdir(currentPath):
                # this is a directory, so go into it
                currentPath=currentPath+os.sep+level
            elif os.path.isfile(currentPath):
                # this is a file... possibly with more stuff in it
                return None # TODO: need to pass this up into the formats bin to read.
                #         If there is anything left in split[] then we need to pass that in as well!
            else:
                # This isn't an actual location.  Is it a glob?
                import glob
                foundAny=False
                for filename in glob.glob(currentPath):
                    foundAny=True
                    # TODO: read all these files... and possibly subdirectories
                if not foundAny:
                    print(f'File "{locationString}" not found.  ("{currentPath}") does not exist.')
        return None

    def _isRootPath(self,path:str)->bool:
        if path and path[0]=='/':
            # linux style
            return True
        if len(path)>1 and path[1]==':':
            # windows style
            return True
        return False

    def _dir(self,url:UrlCompatible)->typing.Generator[OsItem,None,None]:
        """
        get a directory listing
        """
        url=asUrl(url)
        path=url.filePath
        if not path:
            path='.'
        for c in os.listdir(path):
            itemUrl=url.child(c)
            item=self._getFsItem(itemUrl)
            yield item

    def _delete(self,fsItem:OsItem)->None:
        """
        delete an item
        """
        if isinstance(fsItem,OsDirectory):
            # TODO: what about things like zip files that are a file but act like a directory?
            shutil.rmtree(fsItem.fsId)
        else:
            os.remove(fsItem.fsId)
        fsItem.parent.markDirty()

    def _rename(self,fsItem:OsItem,newName:str)->None:
        """
        newName can be either the fully-qualified name, or
        a simple filename to change to
        """
        oldName=asUrl(fsItem)
        newName=oldName.relative(newName)
        oldPath=oldName.url
        newPath=newName
        try:
            os.rename(oldPath,newPath)
        except Exception as e:
            print('ERR: Renaming "'+oldPath+'" to "'+newPath+'"')
            raise e
        if isinstance(fsItem,ezFs.EzFsItem):
            fsItem.url=newName

OsFilesystem=OsFs # alias for convenience