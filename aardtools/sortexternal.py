#!/usr/bin/python
"""
sortexternal.py:  Sort files larger than available memory

There are no restrictions on record contents (e.g. record may contain \n or \x00).
Records do not need to end with \n or \x00.
Records may be up to 2^31 bytes long.

Uses ideas from:
  Title: Sorting big files the Python 2.4 way
  Submitter: Nicolas Lehuen
  http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/466302

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

Copyright (C) 2008  Jeremy Mortis

"""

from heapq import heappop, heappush
import os
import tempfile
import struct
from functools import partial

class VariableLengthRecordFile(file):

    def __init__(self, name, mode, bufsize=-1):
        file.__init__(self, name, mode, bufsize)
        self.headerFormat = "i"
        self.headerLength = struct.calcsize(self.headerFormat)
        self._pack = partial(struct.pack, self.headerFormat)

    def readline(self):
        header = self.read(self.headerLength)
        if header == "":
            return (-2, "")

        recordLength = struct.unpack(self.headerFormat, header)[0]
        if recordLength == -1:
            return (-1, "")

        return (1, self.read(recordLength))

    def writeline(self, s):
        self.write(self._pack(len(s)))
        self.write(s)

    def mark(self):
        self.write(self._pack(-1))

class SortExternal:

    def __init__(self, buffer_size=200000, filenum=16, work_dir=None):
        self.buffer_size = buffer_size
        if work_dir:
            if not os.path.exists(work_dir):
                os.mkdir(work_dir)
            self.work_dir = work_dir
        else:
            self.work_dir = tempfile.mkdtemp()
        self.chunk = []
        self.chunksize = 0

        self.inputChunkFiles = []
        self.outputChunkFiles = []

        for i in range(filenum):
            filename = os.path.join(self.work_dir, "sort-%06i" % i)
            self.inputChunkFiles.append(VariableLengthRecordFile(filename,
                                                                 'w+b',
                                                                 8*1024))
        for i in range(filenum, filenum * 2):
            filename = os.path.join(self.work_dir, "sort-%06i" %i )
            self.outputChunkFiles.append(VariableLengthRecordFile(filename,
                                                                  'w+b',
                                                                  8*1024))

        self.currOutputFile = -1
        self.chunkDepth = 1


    def __iter__(self):
        return self

    def put(self, value):

        self.chunk.append(value)
        self.chunksize += len(value)

        if self.chunksize < self.buffer_size:
            return

        self.chunk.sort()
        self.put_chunk(self.chunk)
        self.chunk = []
        self.chunksize = 0

    def put_chunk(self, valueIterator):

        self.currOutputFile += 1
        if self.currOutputFile >= len(self.outputChunkFiles):
            self.currOutputFile = 0
            self.chunkDepth += 1

        out_file = self.outputChunkFiles[self.currOutputFile]
        for value in valueIterator:
            out_file.writeline(value)
        out_file.mark()

    def sort(self):

        if len(self.chunk) > 0:
            self.chunk.sort()
            self.put_chunk(self.chunk)

        while self.chunkDepth > 1:
            self.mergeFiles()

        t = self.inputChunkFiles
        self.inputChunkFiles = self.outputChunkFiles
        self.outputChunkFiles = t

        for f in self.inputChunkFiles:
            f.flush()
            f.seek(0)

        self.prepareChunkMerge()

    def prepareChunkMerge(self):

        self.chunkHeap = []

        for chunkFile in self.inputChunkFiles:
            status, value = chunkFile.readline()
            if status > 0:
                heappush(self.chunkHeap,(value,chunkFile))

    def mergeFiles(self):

        t = self.inputChunkFiles
        self.inputChunkFiles = self.outputChunkFiles
        self.outputChunkFiles = t

        self.currOutputFile = -1
        self.chunkDepth = 1

        for f in self.outputChunkFiles:
            f.flush()
            f.truncate(0)
            f.seek(0)

        for f in self.inputChunkFiles:
            f.flush()
            f.seek(0)

        # for each layer of chunks
        while True:
            self.prepareChunkMerge()
            if not self.chunkHeap:
                break
            self.put_chunk(self)

    def next(self):
        # merges current chunk layer
        if not self.chunkHeap:
            raise StopIteration

        value, chunkFile = heappop(self.chunkHeap)

        returnValue = value
        status, value = chunkFile.readline()
        if status > 0:
            heappush(self.chunkHeap, (value, chunkFile))

        return returnValue


    def cleanup(self):

        for chunkFile in self.inputChunkFiles:
            chunkFile.close()
            os.remove(chunkFile.name)

        for chunkFile in self.outputChunkFiles:
            chunkFile.close()
            os.remove(chunkFile.name)

        os.rmdir(self.work_dir)
