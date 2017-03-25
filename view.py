from OpenGL.GL import *
import random,numpy,cmath,math,pygame

import ui,globals,drawing,os,copy
from globals.types import Point
import random


class PlayerData(ui.UIElement):
    margin = Point(0,0.1)
    unselected = (0, 0, 0.4, 1.0)
    selected = (1, 0.5, 0, 1)
    players = 'Fiz Gig', 'Tallin Erris', 'Brottor Strakeln', 'Cirefus'
    def __init__(self, parent, pos, tr, name, initial_time):
        if not name:
            name = 'unknown'
        if any((name.startswith(player) for player in self.players)):
            self.unselected = (0.5, 0.5, 0.9, 1.0)
            self.selected = (1,1,0,1)
        self.full_name = name
        name = self.sanitise_name(name)

        if '(' in name:
            #remove the last brackets
            name = name[:name.rfind('(')]
        self.name = name
        self.is_selected = False
        self.last = None

        super(PlayerData, self).__init__( parent, pos, tr )
        bl = Point(0,self.margin.y)
        tr = Point(1,1.0 - self.margin.y)
        self.box = ui.Box(self, bl, tr, colour=self.unselected)
        #self.overlay = ui.Box(self.box, Point(0,0), Point(1,1), colour=(1,0,0,0.5), level=0.1)
        abs_height = self.box.absolute.size.y
        self.scale = min(30, globals.text_manager.GetScale(abs_height*0.95))
        text_height = globals.text_manager.GetSize(self.name, self.scale)
        rel_height = text_height.y / float(abs_height)
        self.text_margin = (1.0 - rel_height)/2.0
        self.text_margin *= 0.9
        print text_height, rel_height, self.text_margin, self.box.absolute.size

        #How much space do we need for the time?
        
        self.text = ui.TextBox(self.box, 
                               bl = Point(0,self.text_margin),
                               tr = Point(1 ,1 - self.text_margin),
                               text = self.name,
                               scale = self.scale,
                               colour = self.selected,
                               alignment = drawing.texture.TextAlignments.LEFT)

        
        self.time_text = None
        self.time_str = None
        self.clock_width = None 
        self.set_time(initial_time)

    def sanitise_name(self,name):
        #If there's a part in double square brackets use that, otherwise use generic
        if any((name.startswith(player) for player in self.players)):
            return name
        if '[[' in name:
            hidden_name = name.split('[[')[1].split(']]')
            full_name = ''.join(hidden_name).split('(')[0]
            return full_name

        return 'Mysterious Monster'


    def add_time(self, t):
        self.time_taken += t
        
        self.update_time()

    def set_time(self, t):
        self.time_taken = t
        self.update_time()

    def update_time(self):
        seconds = self.time_taken / 1000
        if seconds > 3600:
            hours = seconds / 3600
            minutes = (seconds / 60) % 60
            seconds = seconds % 60
            time_str = '%d:%02d:%02d' % (hours, minutes, seconds)
        else:
            minutes = (seconds / 60) % 60
            seconds = seconds % 60
            time_str = '%02d:%02d' % (minutes, seconds)

        time_width = globals.text_manager.GetSize(time_str, self.scale).x
        clock_width = time_width / float(self.box.absolute.size.x)
        colour = self.unselected if self.is_selected else self.selected
        if clock_width != self.clock_width:
            #Probably gone up to hours. Sheesh!
            if self.time_text:
                self.time_text.Delete()
            self.clock_width = clock_width
            self.time_text = ui.TextBox(self.box,
                                        bl = Point(1 - self.clock_width, self.text_margin),
                                        tr = Point(1, 1 - self.text_margin),
                                        text = time_str,
                                        scale = self.scale,
                                        colour = colour, 
                                        alignment = drawing.texture.TextAlignments.RIGHT)
            self.text_items = (self.text, self.time_text)
            self.time_str = time_str
        elif time_str != self.time_str:
            #We can just update it in place
            self.time_text.SetText(time_str, colour=colour)
            self.time_str = time_str

    def set_gone(self):
        if self.is_selected:
            #This really shouldn't happen
            return
        self.box.SetColour( tuple([v*0.5 for v in self.unselected]) )
        for item in self.text_items:
            item.SetColour( tuple([v*0.5 for v in self.selected]) )

    def set_ready(self):
        self.box.bottom_left += Point(0.1,0)
        self.box.top_right += Point(0.1, 0)

        self.box.UpdatePosition()

    def select(self):
        self.is_selected = True
        self.box.SetColour(self.selected)
        for item in self.text_items:
            item.SetColour(self.unselected)

    def unselect(self):
        self.is_selected = False
        self.box.SetColour(self.unselected)
        for item in self.text_items:
            item.SetColour(self.selected)

    def Destroy(self):
        self.box.Delete()
        #self.overlay.Delete()
        
class TurnTime(PlayerData):
    unselected = (0.2, 1, 0.2, 1.0)
    selected = (0, 0, 0.4, 1)

    def sanitise_name(self, name):
        return name

    def __init__(self, parent, pos, tr):
        super(TurnTime, self).__init__(parent, pos, tr, 'Turn Time:', 0)
        

class GameView(ui.RootElement):
    min_len = 6
    margin = Point(0.05,0.05)
    padding = 0.05
    def __init__(self):
        self.atlas = globals.atlas = drawing.texture.TextureAtlas('tiles_atlas_0.png','tiles_atlas.txt')
        self.game_over = False
        self.last = None
        #pygame.mixer.music.load('music.ogg')
        #self.music_playing = False
        super(GameView,self).__init__(Point(0,0),globals.screen)
        #skip titles for development of the main game
        #self.box = ui.Box(self, Point(0.1,0.1), Point(0.8,0.8), colour=(1,0,0,1))
        self.items = []
        self.turn_time = None
        self.chosen = None
        #self.set_items(['Fiz Gig','Tallin Erris','Brottor Strakeln','Cirefus'], 3, 1)
        self.times = {}

    def hide(self):
        self.clear_items()

    def set_items(self, name_list, chosen, num_gone):
        self.clear_items()
        display_len = len(name_list) + 1
        if display_len < self.min_len:
            display_len = self.min_len
        top = 1.0 - self.margin.y
        bottom = self.margin.y
        height_per_name = (top - bottom) / display_len

        self.turn_time = TurnTime( self, 
                                   Point(self.margin.x, top - height_per_name),
                                   Point(1.0 - self.margin.x, top) )

        for pos,name in enumerate(name_list):
            i = pos + 1

            t = self.times.get(name,0)
                
            entry = PlayerData(self, 
                               Point(self.margin.x, top - (i+1)*height_per_name),
                               Point(1.0 - self.margin.x, top - i*height_per_name),
                               name, initial_time=t)
            self.items.append(entry)

        if chosen >= len(self.items):
            chosen = len(self.items) - 1
        if num_gone >= len(self.items):
            num_gone = len(self.items) - 1

        self.chosen = chosen
        self.items[chosen].select()
        for i in xrange(num_gone):
            self.items[i].set_gone()

        for i in xrange(num_gone, chosen):
            self.items[i].set_ready()
        
    def clear_items(self):
        if self.turn_time:
            self.turn_time.Destroy()
        for item in self.items:
            self.times[item.full_name] = item.time_taken
            item.Destroy()
        self.items = []

    def Draw(self):
        drawing.ResetState()
        drawing.Translate(0,0,0)
        #drawing.DrawNoTexture(globals.line_buffer)
        #drawing.DrawNoTexture(globals.colour_tiles)
        #drawing.DrawAll(globals.quad_buffer,self.atlas.texture)
        drawing.DrawAll(globals.nonstatic_text_buffer,globals.text_manager.atlas.texture.texture)

    def Update(self):
        if self.game_over:
            return

        if self.last is None:
            self.last = globals.time
            return

        elapsed = globals.time - self.last
        self.last = globals.time
            
        if globals.paused:
            return

        try:
            if self.chosen is not None:
                self.items[self.chosen].add_time(elapsed)
        except IndexError:
            return
        if self.turn_time:
            self.turn_time.add_time(elapsed)

    def GameOver(self):
        self.game_over = True
        self.mode = modes.GameOver(self)

    def KeyDown(self,key):
        pass

    def KeyUp(self,key):
        pass

class ImageView(ui.RootElement):
    fade_start = 5000
    fade_end   = 8000
    zoom_start = 1.0
    zoom_end   = 1.05
    zoom_amount = zoom_end - zoom_start

    def __init__(self):
        super(ImageView,self).__init__(Point(0,0),globals.screen)
        #We have two quads, one for the current image and one for the next
        self.current_buffer = drawing.QuadBuffer(16)
        self.next_buffer    = drawing.QuadBuffer(16)
        self.current_quad = drawing.Quad(self.current_buffer, tc=drawing.constants.full_tc)
        self.next_quad    = drawing.Quad(self.next_buffer, tc=drawing.constants.full_tc)
        self.set_colour( (1,1,1) )

        self.current_quad.SetVertices( self.absolute.bottom_left, self.absolute.top_right, 1)
        self.next_quad.SetVertices( self.absolute.bottom_left, self.absolute.top_right, 2)
        #Load the names of all the images we might be using
        self.screens = {}
        for screen in os.listdir('resource'):
            images = []
            dirname = os.path.join( 'resource', screen )
            for image in os.listdir( dirname ):
                images.append( os.path.join(dirname, image) )
            if len(images) == 0:
                continue
            self.screens[screen] = images

        self.current_texture = None
        self.next_texture = None
        self.set_dir('main')
        

    def set_colour(self, colour):
        self.colour = colour

    def hide(self):
        self.current_quad.Disable()
        self.next_quad.Disable()

    def set_dir(self, dirname):
        self.current_quad.Enable()
        self.next_quad.Enable()
        #To start things off we load the first and second images into separate textures
        self.current_screen = dirname
        self.current_images = list(self.screens[self.current_screen])
        random.shuffle(self.current_images)
        for texture in self.current_texture, self.next_texture:
            if texture:
                texture.delete()

        self.fade = len(self.current_images) > 1
        self.current_texture = self.get_next_texture(self.current_quad)
        self.next_texture = self.get_next_texture(self.next_quad)
        self.current_quad.SetColour( self.colour + (1,) )
        self.next_quad.SetColour( self.colour + (0,) )

        if self.fade:
            self.current_quad.SetVertices( Point(0,0), globals.screen, 1)

        self.start_time = None
        self.next_images = None
        

    def change_dir(self, dirname):
        if dirname == self.current_screen:
            return
        self.next_screen = dirname
        #If we're currently on a screen, we want to change the next image to come from the new set immediately
        if self.start_time is None:
            #This should only happen during the first frame
            self.start_time = globals.time
        elapsed = globals.time - self.start_time

    def get_next_texture(self, quad):
        try:
            image = self.current_images.pop(0)
        except IndexError:
            self.current_images = list(self.screens[self.current_screen])
            random.shuffle(self.current_images)
            image = self.current_images.pop(0)
        
        new = drawing.texture.Texture(image)
        quad.SetTextureCoordinates( new.get_full_tc(globals.screen, self.fade) )
        return new

    def Update(self):
        if self.start_time is None:
            self.start_time = globals.time
            return
        if not self.fade:
            #Fixed image
            return
        elapsed = globals.time - self.start_time
        current_opacity = 1
        next_opacity = 0
        current_scale = self.zoom_end + self.zoom_amount*(float(elapsed) / self.fade_end)
        next_scale = self.zoom_start
        if elapsed > self.fade_end:
            #We've finished fading
            self.start_time = globals.time
            if self.current_texture:
                self.current_texture.delete()
            self.current_texture = self.next_texture
            #self.current_quad.SetTextureCoordinates( self.current_texture.get_full_tc(globals.screen) )
            self.current_quad.SetTextureCoordinates( self.next_quad.GetTextureCoordinates() )
            self.next_texture = self.get_next_texture(self.next_quad)
            current_scale = self.zoom_end
        elif elapsed > self.fade_start:
            fade_partial = float(elapsed - self.fade_start) / (self.fade_end - self.fade_start)
            next_opacity = fade_partial
            next_scale = self.zoom_start + self.zoom_amount*fade_partial
            current_opacity = 1-fade_partial
        
        self.current_quad.SetColour( self.colour + (current_opacity,) )
        self.next_quad.SetColour( self.colour + (next_opacity,) )

        #Maybe skip this
        bl = -0.5*current_scale + 0.5
        tr = 0.5*current_scale + 0.5
        self.current_quad.SetVertices( globals.screen*bl, globals.screen*tr, 1)
        scale = next_opacity
        bl = -0.5*next_scale + 0.5
        tr = 0.5*next_scale + 0.5
        self.next_quad.SetVertices( globals.screen*bl, globals.screen*tr, 2)
            
    def KeyDown(self,key):
        pass

    def KeyUp(self,key):
        pass

    def Draw(self):
        drawing.ResetState()
        drawing.Translate(0,0,0)
        #drawing.DrawNoTexture(globals.line_buffer)
        #drawing.DrawNoTexture(globals.colour_tiles)
        drawing.DrawAll(self.current_buffer,self.current_texture.texture)
        drawing.DrawAll(self.next_buffer,self.next_texture.texture)
        #drawing.DrawAll(globals.nonstatic_text_buffer,globals.text_manager.atlas.texture.texture)
