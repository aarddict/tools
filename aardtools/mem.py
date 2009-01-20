# From http://snipplr.com/view/6460/get-memory-usage-of-current-process-on-unix/
"""
Trivial, but working code to get the memory usage of the current process
where the pid is retrieved using os.getpid() and the memory usage is read
from the unix command ps.    
"""

import os

__version__ = "1.0"
__author__ = "Florian Leitner"

def mem(size="rss", pid=None):
    """Generalization; memory sizes: rss, rsz, vsz."""
    if not pid:
        pid = os.getpid()
    return int(os.popen('ps -p %d -o %s | tail -1' %                                                                     
                        (pid, size)).read())                                                                             
                                                                                                                         
def rss(pid=None):
    """Return ps -o rss (resident) memory in kB."""
    return mem("rss", pid)
                                                                                                                         
def rsz(pid=None):
    """Return ps -o rsz (resident + text) memory in kB."""
    return mem("rsz", pid)

def vsz(pid=None):
    """Return ps -o vsz (virtual) memory in kB."""
    return mem("vsz", pid)
