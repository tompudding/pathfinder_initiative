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

def parse_name(name):
    if not name.startswith('{'):
        raise ValueError()
    return [part for part in name.split('}') if part[0] != '{'][0].split('\x00')[0]
        
class Actor(object):
    def __init__(self, pid, name_ptr, init_ptr, order_ptr):
        self.pid       = pid
        self.name_ptr  = name_ptr
        self.init_ptr  = init_ptr
        self.order_ptr = order_ptr
        self.init      = None
        self.order     = None
        self.name      = None
        self.refresh()

    def refresh(self):
        "Reload properties and return True if anything has changed"
        init  = vmaccess.vm_read_word(self.pid, self.init_ptr)
        order = vmaccess.vm_read_word(self.pid, self.order_ptr)
        name_ptr = vmaccess.vm_read_word(self.pid, self.name_ptr)
        name  = vmaccess.vm_read(self.pid, name_ptr, 128)
        name  = parse_name(name)
        if (self.init, self.order, self.name) != (init, order, name):
            self.init, self.order, self.name = init, order, name
            return True
        return False

    def __eq__(self, other):
        if self.name != other.name:
            return False
        if self.init != other.init:
            return False
        if self.order != other.order:
            return False

        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return 'init=%2d order=%2d name=%s' % (self.init, self.order, self.name)

class HeroData(object):
    def __init__(self, pid, count_ptr, actors):
        self.pid = pid
        self.count_ptr = count_ptr
        self.actors = sorted(actors, lambda x,y : cmp(y.init, x.init))

    def __eq__(self, other):
        if other == None:
            return False
        if len(self.actors) != len(other.actors):
            return False

        for a,b in zip(self.actors, other.actors):
            if a != b:
                return False
            
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return '\n'.join(str(actor) for actor in self.actors)

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
            #print '%08x - %08x : %s' % (map.start, map.end, map.filename)
            matches.append((pos - 1, map))
            
    #print 'Have %d matches for initiative needle' % len(matches)
    #for offset in xrange(0x84, 0x85, 4):
    offset = 0x84
    total_estimates = set()
    actors = []
    for pos,src_map in matches:
        references = []
        needle = struct.pack('<I',pos - offset)
        for map in maps:
            references.extend([ref for ref in map.scan(needle)])

        if len(references) < 2:
            continue

        for ref in references:
            name_ptr = vmaccess.vm_read_word(pid, ref - 0x478)

            if name_ptr < 0x8000:
                continue
            try:
                name = vmaccess.vm_read(pid, name_ptr, 128)
            except RuntimeError:
                continue
            try:
                name = parse_name(name)
            except:
                continue
            break
        else:
            name = 'unknown'
            name_ptr = None
            ref = None

        actor = Actor(pid       = pid,
                      name_ptr  = ref - 0x478,
                      init_ptr  = pos,
                      order_ptr = pos - 0x44)
        actors.append(actor)
            
        common  = vmaccess.vm_read_word(pid, pos-0x48)
        num_ptr = vmaccess.vm_read_word(pid, common + 4) + 0x164
        num = vmaccess.vm_read_word(pid, num_ptr)
        total_estimates.add( (num_ptr, num) )

    if len(total_estimates) != 1:
        raise RuntimeError('Got more than one guess at the number of participants')
    count_ptr, count = total_estimates.pop()
    if len(actors) != count:
        raise RuntimeError('Error, got %d actors but expected %d' % (len(actors), count))

    return HeroData(pid, count_ptr, actors)

import time

pids = [pid for pid in pidof('HeroLab.exe')]

if len(pids) != 1:
    raise SystemExit('More than one Hero Lab!')

def is_candidate_map(map):
    if not map.perms.writable:
        return False
    if map.filename:
        return False
    return True
        

last_data = None
used_maps = []
while True:
    writable_maps = [map for map in maps(pid) if is_candidate_map(map)]

    hero_data = scan_initiative(pid, writable_maps)

    if hero_data != last_data:
        print hero_data

    last_data = hero_data

    time.sleep(4)

    
