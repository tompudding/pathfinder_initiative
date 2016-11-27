import vmaccess
import os
import glob
import hashlib

class Perms(object):
    def __init__(self, perms_string):
        self.readable = perms_string[0] == 'r'
        self.writable = perms_string[1] == 'w'
        self.executable = perms_string[2] == 'x'

class Region(object):
    def __init__(self, start, end, perms, filename):
        self.start = start
        self.end = end
        self.perms = perms
        self.filename = filename
        

def maps(pid):
    with open('/proc/%d/maps' % pid, 'rb') as f:
        for line in f:
            try:
                addrs, perms, size, dev, rest = line.strip().split(None, 4)
            except ValueError:
                continue
            try:
                inode, filename = rest.split(None, 1)
            except ValueError:
                filename = ''
            start,end = (int(addr,16) for addr in addrs.split('-'))
            perms = Perms(perms)
            yield Region(start, end, perms, filename)

def pidof(name):
    for cmdline in glob.glob('/proc/*/cmdline'):
        try:
            pid = cmdline.split('/')[2]
        except IndexError:
            continue

        try:
            pid = int(pid)
        except ValueError:
            continue

        with open(cmdline, 'rb') as f:
            data = f.read()
            if name in data:
                yield pid

def scan_pid(pid, maps):
    hashes = {}
    changing_pages = set()
    #Let's pull in each page in every map and hash it
    for trial in xrange(1000):
        for map in maps:
            for page in xrange(map.start, map.end, 0x100):
                try:
                    region = vmaccess.vm_read(pid, page, 0x100)
                except RuntimeError:
                    continue
                hash = hashlib.md5(region).digest()
                if page in hashes:
                    if hashes[page] != hash:
                        changing_pages.add(page)
                else:
                    hashes[page] = hash
        print 'complete',len(hashes),len(changing_pages)
            

for pid in pidof('HeroLab.exe'):
    def is_candidate_map(map):
        if not map.perms.writable:
            return False
        if '.dll' in map.filename.lower():
            return False
        return True
        
    writable_maps = [map for map in maps(pid) if is_candidate_map(map)]
    for map in writable_maps:
        print hex(map.start),hex(map.end),map.filename

    scan_pid(pid, writable_maps)
