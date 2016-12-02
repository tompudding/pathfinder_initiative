import vmaccess
import os
import glob
import hashlib
import time
import struct

class Perms(object):
    def __init__(self, perms_string):
        self.readable = perms_string[0] == 'r'
        self.writable = perms_string[1] == 'w'
        self.executable = perms_string[2] == 'x'

class Region(object):
    def __init__(self, pid, start, end, perms, filename):
        self.pid = pid
        self.start = start
        self.end = end
        self.perms = perms
        self.filename = filename

    def scan(self, needle):
        try:
            region = vmaccess.vm_read(self.pid, self.start, self.end - self.start)
        except RuntimeError:
            return
        region_pos = 0
        while region_pos < len(region):
            try:
                region_pos = region.index(needle, region_pos)
            except ValueError:
                break
            #print hex(page + region_pos),hex(struct.unpack('<I',region[region_pos-1:region_pos+3])[0])
            yield self.start + region_pos
            region_pos += 1
        

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
            yield Region(pid, start, end, perms, filename)

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

def dump(data, addr):
    fmt = '%08x : ' + (' '.join(['%08x' for i in xrange(4)]))
    pos = 0
    while pos + 16 <= len(data):
        print fmt % ((addr + pos,) + tuple(struct.unpack('<I',data[p:p+4])[0] for p in xrange(pos,pos+16,4)))
        pos += 16

    left = len(data) - pos
    fmt = '%08x : ' + (' '.join(['%02x' for i in xrange(left)]))
    print fmt % ((addr,) + tuple(ord(b) for b in data[pos:]))

def scan_initiative(pid, maps):
    #Scan the writable regions for the initiative signature
    needle = '\x00\x00\x00' + struct.pack('<III',2**32-99,99,1)
    matches = []
    for map in maps:
        for pos in map.scan(needle):
            init = vmaccess.vm_read(pid, pos-0x1, 0x1)
            matches.append((pos - 1, ord(init), map))
            
    #print 'Have %d matches for initiative needle' % len(matches)
    #for offset in xrange(0x84, 0x85, 4):
    offset = 0x84
    for pos,init,src_map in matches:
        references = []
        needle = struct.pack('<I',pos - offset)
        for map in maps:
            references.extend([ref for ref in map.scan(needle)])
        if len(references) != 2:
            continue

        name_ptr = vmaccess.vm_read(pid, references[0] - 0x478, 4)
        name_ptr = struct.unpack('<I',name_ptr)[0]
        if name_ptr < 0x8000:
            continue
        name = vmaccess.vm_read(pid, name_ptr, 128)
        name = [part for part in name.split('}') if part[0] != '{'][0].split('\x00')[0]
            
        region = vmaccess.vm_read(pid, pos-0x84, 0x100)
        # with open('/tmp/bin.bin','ab') as f:
        #     f.write(region)
        order = struct.unpack('<I',region[0x40:0x44])[0]
        print 'init=%2d pos=%d name=%s' % (init, order, name)

def scan_name(pid, maps):
    import binascii
    needle = 'Brottor Strakeln'.encode('utf-16')[2:]
    print binascii.hexlify(needle)
    for map in maps:
        for pos in map.scan(needle):
            print 'Brottor at %08x' % pos
    
def scan_pid(pid, maps):
    matches = []
    needle = '\x41\x00\x00\x00'
    needle = '\xd8\x57\xad\x19'
    candidates = {}
    for map in maps:
        for page in xrange(map.start, map.end, 0x1000):
            try:
                region = vmaccess.vm_read(pid, page, 0x1000)
            except RuntimeError:
                continue
            region_pos = 0
            while region_pos < len(region):
                try:
                    region_pos = region.index(needle, region_pos)
                except ValueError:
                    break
                print hex(page + region_pos),hex(struct.unpack('<I',region[region_pos-1:region_pos+3])[0])
                matches.append((page + region_pos, map))
                candidates[page+region_pos] = map
                region_pos += 1
    print 'complete',len(matches)

    # candidates = {}
    # done = False
    # good_passes = 0
    # while not done:
    #     good_pass = False
    #     for pos,map in matches:
    #         val = vmaccess.vm_read(pid, pos, 0x4)
    #         if val == '\x61\x00\x00\x00':
    #             print 'BINGO %08x %08x-%08x %s' % (pos, map.start, map.end, map.filename) 
    #             candidates[pos] = map
    #             good_pass = True
    #     if good_pass:
    #         good_passes += 1
    #     if good_passes > 6:
    #         done = True
    #     time.sleep(0.5)

    #dump the memory around these candidates
    for pos,map in candidates.iteritems():
        base = (pos - 64)&0xfffffffc
        region = vmaccess.vm_read(pid, base, 128)
        dump(region, base)
        print

            

for pid in pidof('HeroLab.exe'):
    def is_candidate_map(map):
        if not map.perms.writable:
            return False
        if '.dll' in map.filename.lower():
            return False
        return True
        
    writable_maps = [map for map in maps(pid) if is_candidate_map(map)]
    #for map in writable_maps:
    #    print hex(map.start),hex(map.end),map.filename

    scan_initiative(pid, writable_maps)
    #scan_name(pid, writable_maps)
