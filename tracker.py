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

    def __eq__(self, other):
        return self.readable == other.readable and self.writable == other.writable and self.executable == other.executable

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self.readable, self.writable, self.executable))

    def __repr__(self):
        return ''.join(letter if val else '.' for (letter,val) in (('r',self.readable),
                                                                   ('w',self.writable),
                                                                   ('x',self.executable)))

class Region(object):
    def __init__(self, pid, start, end, perms, filename):
        self.pid = pid
        self.start = start
        self.end = end
        self.perms = perms
        self.filename = filename.strip()

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

    def __eq__(self, other):
        return self.start == other.start and self.end == other.end and self.perms == other.perms and self.filename == other.filename

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return '%08x - %08x : %s : %s' % (self.start, self.end, self.perms, self.filename)

    def __hash__(self):
        return hash((self.start, self.end, self.perms, self.filename))

def parse_name(name):
    if not name.startswith('{'):
        raise ValueError()
    out = [part for part in name.split('}') if part and part[0] != '{'][0].split('\x00')
    return out[0]
        
class Actor(object):
    def __init__(self, pid, name, init_ptr, order_ptr):
        self.pid       = pid
        self.name      = name
        self.init_ptr  = init_ptr
        self.order_ptr = order_ptr
        self.init = None
        self.order = None
        self.refresh()

    def refresh(self):
        "Reload properties and return True if anything has changed"
        init  = vmaccess.vm_read_word(self.pid, self.init_ptr)
        order = vmaccess.vm_read_word(self.pid, self.order_ptr)
        
        if (self.init, self.order) != (init, order):
            self.init, self.order = init, order
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

    def scan_for_changes(self):
        if vmaccess.vm_read_word(self.pid, self.count_ptr) != len(self.actors):
            return True
        updated = False
        for actor in self.actors:
            if actor.refresh():
                updated = True

        return updated

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

def scan_initiative(pid, maps, bad_maps):
    #Scan the writable regions for the initiative signature
    needle = '\x00\x00\x00' + struct.pack('<III',2**32-99,99,1)
    matches = []
    for map in maps:
        if map in bad_maps:
            continue
        count = 0
        for pos in map.scan(needle):
            #print '%08x - %08x : %s' % (map.start, map.end, map.filename)
            matches.append((pos - 1, map))
            count += 1
        if count == 0:
            bad_maps.add(map)
            
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
                name_data = vmaccess.vm_read(pid, name_ptr, 4096)
            except RuntimeError:
                continue
            
            try:
                name = parse_name(name_data)
            except:
                continue
            print name
            if 'Tallin' in name:
                with open('/tmp/tallin.bin','wb') as f:
                    f.write(name_data)
            try:
                t = name_data.split('\x00')
                print t[0],'::',t[13],'::',t[19],name_data.startswith('{text clrdisable}')
            except:
                pass
            break
        else:
            name = 'unknown'

        actor = Actor(pid       = pid,
                      name      = name,
                      init_ptr  = pos,
                      order_ptr = pos - 0x44)

        try:
            common  = vmaccess.vm_read_word(pid, pos-0x48)
            num_ptr = vmaccess.vm_read_word(pid, common + 4) + 0x164
            num = vmaccess.vm_read_word(pid, num_ptr)
        except RuntimeError:
            continue
        actors.append(actor)
        total_estimates.add( (num_ptr, num) )

    if len(total_estimates) != 1:
        print total_estimates
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

def main():
    last_data = None
    bad_maps = set()
    while True:
        writable_maps = [map for map in maps(pid) if is_candidate_map(map) and not map in bad_maps]

        print 'scanning %d maps, %d bad ones' % (len(writable_maps), len(bad_maps))
        try:
            hero_data = scan_initiative(pid, writable_maps, bad_maps)
        except RuntimeError as e:
            bad_maps = set()
            continue
        print 'scanned'

        if hero_data != last_data:
            print hero_data
            print

        last_data = hero_data

        while True:
            if hero_data.scan_for_changes():
                print 'change detected'
                break
            time.sleep(0.1)

main()
