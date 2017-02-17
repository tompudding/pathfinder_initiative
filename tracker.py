import vmaccess
import os
import glob
import hashlib
import time
import struct
import socket
import multiprocessing
import globals
import messages

#remote_addr = ("192.168.144.251", 4919)
remote_addr = ("127.0.0.1", 4919)

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
        raise RuntimeError()
    selected = name.startswith('{text clrbright}')
    gone = name.startswith('{text clrdisable}')
    out = [part for part in name.split('}') if part and part[0] != '{'][0].split('\x00')
    return out[0],selected,gone
        
class Actor(object):
    def __init__(self, pid, name, selected, gone, init_ptr, order_ptr, name_ptr):
        self.pid       = pid
        self.name      = name
        self.selected  = selected
        self.gone      = gone
        self.init_ptr  = init_ptr
        self.order_ptr = order_ptr
        self.name_ptr  = name_ptr
        self.init = None
        self.order = None
        self.refresh()

    def refresh(self):
        "Reload properties and return True if anything has changed"
        init  = vmaccess.vm_read_word(self.pid, self.init_ptr)
        order = vmaccess.vm_read_word(self.pid, self.order_ptr)
        name_data = vmaccess.vm_read(pid, self.name_ptr, 1024)
        name,selected,gone = parse_name(name_data)
        
        if (self.init, self.order, self.name, self.selected, self.gone) != (init, order, name, selected, gone):
            self.init, self.order, self.name, self.selected, self.gone = init, order, name, selected, gone
            return True
        return False

    def __eq__(self, other):
        if self.name != other.name:
            return False
        if self.init != other.init:
            return False
        if self.order != other.order:
            return False
        if self.selected != other.selected:
            return False

        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        if self.gone:
            extra = '---'
        elif self.selected:
            extra = '***'
        else:
            extra = ''
        return 'init=%2d order=%2d name=%s %s' % (self.init, self.order, self.name, extra )


players = 'Fiz Gig', 'Tallin Erris', 'Brottor Strakeln', 'Cirefus'

def sanitise_name(name):
    #If there's a part in double square brackets use that, otherwise use generic
    if any((name.startswith(player) for player in players)):
        return name
    if '[[' in name:
        hidden_name = name.split('[[')[1].split(']]')
        full_name = ''.join(hidden_name).split('(')[0]
        return full_name
    
    return 'Mysterious Monster'

class HeroData(object):
    def __init__(self, pid, count_ptr, actors):
        self.pid = pid
        self.count_ptr = count_ptr
        self.actors = sorted(actors, lambda x,y : cmp(x.order, y.order))
        gone = [actor for actor in self.actors if actor.gone]
        not_gone = [actor for actor in self.actors if not actor.gone]
        self.num_gone = len(gone)
        self.actors = gone + not_gone

    def scan_for_changes(self):
        if vmaccess.vm_read_word(self.pid, self.count_ptr) != len(self.actors):
            return True
        updated = False
        for actor in self.actors:
            if actor.refresh():
                updated = True

        return updated

    def send(self):
        for i, actor in enumerate(self.actors):
            if actor.selected:
                break
        else:
            i = 0xff
        chosen = i
        buffer = chr(messages.MessageType.GAME_MODE) + chr(chosen) + chr(self.num_gone) + '\x00'.join( (sanitise_name(actor.name) for actor in self.actors))
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        #now connect to the web server on port 80
        # - the normal http port
        try:
            s.connect(remote_addr)
            s.send(buffer)
        except socket.error as e:
            print 'Error connecting'
            pass

        s.close()
        


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
        #if bad_maps:
        #    print 'scanning %08x - %08x : %s %d' % (map.start, map.end, map.filename, len(bad_maps))
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
            matches = [ref for ref in map.scan(needle)]
            references.extend(matches)
            if matches and map in bad_maps:
                bad_maps.remove(map)

        if len(references) < 2:
            continue

        for ref in references:
            name_ptr = vmaccess.vm_read_word(pid, ref - 0x430)

            if name_ptr < 0x8000:
                continue
            try:
                name_data = vmaccess.vm_read(pid, name_ptr, 512)
            except RuntimeError:
                continue
                try:
                    print 'trying with len',0x1000 - (name_ptr&0xfff)
                    name_data = vmaccess.vm_read(pid, name_ptr, 0x1000 - (name_ptr&0xfff))
                except RuntimeError:
                    continue

            try:
                name,selected,gone = parse_name(name_data)
            except:
                continue

            #print name,selected
            # if 'Tallin' in name:
            #     with open('/tmp/tallin.bin','wb') as f:
            #         f.write(name_data)
            # try:
            #     t = name_data.split('\x00')
            #     print t[0],'::',t[13],'::',t[19],name_data.startswith('{text clrdisable}')
            # except:
            #     pass
            break
        else:
            name = 'unknown'
            selected = False
            gone = False

        actor = Actor(pid       = pid,
                      name      = name,
                      selected  = selected,
                      gone      = gone,
                      init_ptr  = pos,
                      order_ptr = pos - 0x44,
                      name_ptr  = name_ptr)

        try:
            common  = vmaccess.vm_read_word(pid, pos-0x48)
            num_ptr = vmaccess.vm_read_word(pid, common + 4) + 0x164
            num = vmaccess.vm_read_word(pid, num_ptr)
        except RuntimeError:
            continue
        actors.append(actor)
        #print 'Match on map %08x - %08x : %s' % (src_map.start, src_map.end, src_map.filename)
        total_estimates.add( (num_ptr, num) )

    if len(total_estimates) != 1:
        print total_estimates
        raise RuntimeError('Got more than one guess at the number of participants')
    count_ptr, count = total_estimates.pop()
    if len(actors) != count:
        print 'blarg',len(actors),count
        for actor in actors:
            print actor
        raise RuntimeError('Error, got %d actors but expected %d' % (len(actors), count))

    return HeroData(pid, count_ptr, actors)

import time

pids = [pid for pid in pidof('HeroLab.exe')]

if len(pids) != 1:
    raise SystemExit('More than one Hero Lab!')

def is_candidate_map(map):
    if not map.perms.writable:
        return False
    #if map.filename:
    #    return False
    return True

globals.scanning = False
globals.running = True

def scan_main():
    last_data = None
    bad_maps = set()
    while True:
        writable_maps = [map for map in maps(pid) if is_candidate_map(map) and not map in bad_maps]

        print 'scanning %d maps, %d bad ones' % (len(writable_maps), len(bad_maps))
        try:
            hero_data = scan_initiative(pid, writable_maps, bad_maps)
        except RuntimeError as e:
            #raise e
            bad_maps = set()
            continue
        print 'scanned'

        if hero_data != last_data:
            print hero_data
            hero_data.send()
            print

        last_data = hero_data

        while True:
            slept = 0
            try:
                if hero_data.scan_for_changes():
                    print 'change detected'
                    break
                time.sleep(0.1)
                slept += 1
                if slept >= 20:
                    slept = 0
                    hero_data.send()
            except:
                break

import cursesmenu
import sys

class StdOutWrapper:
    text = []
    def write(self,txt):
        self.text.append(txt)
        if len(self.text) > 500:
            self.text = self.text[:500]
    def get_text(self):
        return ''.join(self.text)

    def flush(self):
        pass

def start_game_mode():
    if globals.game_process:
        return
    globals.game_process = multiprocessing.Process(target=scan_main)
    globals.game_process.start()

def get_scene_list():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    #now connect to the web server on port 80
    # - the normal http port
    try:
        s.connect(remote_addr)
        s.send(chr(messages.MessageType.REQUEST_IMAGE_LIST))
        response = s.recv(1024)
        return response.split('\x00')
    except socket.error as e:
        print 'Error connecting'

def choose_scene(name):
    if globals.game_process:
        #Kill this bad boy
        os.kill(globals.game_process.pid, 9)
        globals.game_process.join()
        globals.game_process = None
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(remote_addr)
        s.send(chr(messages.MessageType.CHOOSE_IMAGE_LIST) + name)
    except socket.error as e:
        print 'Error connecting'

def create_menu():
    # Create the menu
    globals.game_process = None
    menu = cursesmenu.CursesMenu("Pathfinder")

    # Create some items
    options = get_scene_list()
    
    # A FunctionItem runs a Python function when selected
    menu.append_item(cursesmenu.items.FunctionItem("Game Mode", start_game_mode))
    if options is None:
        options = []
    for item in options:
        menu.append_item(cursesmenu.items.FunctionItem(item, choose_scene, (item,)))

    menu.show()

if __name__ == '__main__':
    mystdout = StdOutWrapper()
    sys.stdout = mystdout
    sys.stderr = mystdout
    #create the scanning process
    try:
        create_menu()
    finally:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        sys.stdout.write(mystdout.get_text())



