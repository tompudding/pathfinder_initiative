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
    def __init__(self, parent, pos, tr, name):
        if not name:
            name = 'unknown'
        if any((player in name for player in self.players)):
            self.unselected = (0.5, 0.5, 0.9, 1.0)
            self.selected = (1,1,0,1)
        self.name = name
        self.is_selected = False

        super(PlayerData, self).__init__( parent, pos, tr )
        bl = Point(0,self.margin.y)
        tr = Point(1,1.0 - self.margin.y)
        self.box = ui.Box(self, bl, tr, colour=self.unselected)
        #self.overlay = ui.Box(self.box, Point(0,0), Point(1,1), colour=(1,0,0,0.5), level=0.1)
        abs_height = self.box.absolute.size.y
        scale = min(30, globals.text_manager.GetScale(abs_height*0.95))
        text_height = globals.text_manager.GetSize(self.name, scale)
        rel_height = text_height.y / float(abs_height)
        text_margin = (1.0 - rel_height)/2.0
        text_margin *= 0.9
        print text_height, rel_height, text_margin, self.box.absolute.size
        self.text = ui.TextBox(self.box, 
                               bl = Point(0,text_margin),
                               tr = Point(1,1 - text_margin),
                               text = self.name,
                               scale = scale,
                               colour = self.selected,
                               alignment = drawing.texture.TextAlignments.CENTRE)

    def set_gone(self):
        if self.is_selected:
            #This really shouldn't happen
            return
        self.box.SetColour( tuple([v*0.5 for v in self.unselected]) )
        self.text.SetColour( tuple([v*0.5 for v in self.selected]) )

    def set_ready(self):
        self.box.bottom_left += Point(0.1,0)
        self.box.top_right += Point(0.1, 0)

        self.box.UpdatePosition()

    def select(self):
        self.is_selected = True
        self.box.SetColour(self.selected)
        self.text.SetColour(self.unselected)

    def unselect(self):
        self.is_selected = False
        self.box.SetColour(self.unselected)
        self.text.SetColour(self.selected)

    def Destroy(self):
        self.box.Delete()
        #self.overlay.Delete()
        

class GameView(ui.RootElement):
    min_len = 6
    margin = Point(0.05,0.05)
    padding = 0.05
    def __init__(self):
        self.atlas = globals.atlas = drawing.texture.TextureAtlas('tiles_atlas_0.png','tiles_atlas.txt')
        self.game_over = False
        #pygame.mixer.music.load('music.ogg')
        #self.music_playing = False
        super(GameView,self).__init__(Point(0,0),globals.screen)
        #skip titles for development of the main game
        #self.box = ui.Box(self, Point(0.1,0.1), Point(0.8,0.8), colour=(1,0,0,1))
        self.items = []
        self.chosen = None
        #self.set_items(['Fiz Gig','Tallin Erris','Brottor Strakeln','Cirefus'], 3, 1)

    def hide(self):
        self.clear_items()

    def set_items(self, name_list, chosen, num_gone):
        self.clear_items()
        display_len = len(name_list)
        if display_len < self.min_len:
            display_len = self.min_len
        top = 1.0 - self.margin.y
        bottom = self.margin.y
        height_per_name = (top - bottom) / display_len

        for i,name in enumerate(name_list):
            entry = PlayerData(self, 
                               Point(self.margin.x, top - (i+1)*height_per_name),
                               Point(1.0 - self.margin.x, top - i*height_per_name),
                               name)
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
        for item in self.items:
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

        self.set_dir('main')

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
        self.current_texture = self.get_next_texture(self.current_quad)

        self.next_texture = self.get_next_texture(self.next_quad)

        #Then show the current one
        self.current_quad.SetColour( (1,1,1,1) )
        self.next_quad.SetColour( (1,1,1,0) )
        self.start_time = None

    def get_next_texture(self, quad):
        try:
            image = self.current_images.pop(0)
        except IndexError:
            self.current_images = list(self.screens[self.current_screen])
            random.shuffle(self.current_images)
            image = self.current_images.pop(0)
        
        new = drawing.texture.Texture(image)
        quad.SetTextureCoordinates( new.get_full_tc(globals.screen) )
        return new

    def Update(self):
        if self.start_time is None:
            self.start_time = globals.time
            return
        elapsed = globals.time - self.start_time
        current_opacity = 1
        next_opacity = 0
        current_scale = self.zoom_end + self.zoom_amount*(float(elapsed) / self.fade_end)
        next_scale = self.zoom_start
        if elapsed > self.fade_end:
            #We've finished fading
            self.start_time = globals.time
            self.current_texture = self.next_texture
            self.current_quad.SetTextureCoordinates( self.current_texture.get_full_tc(globals.screen) )
            self.next_texture = self.get_next_texture(self.next_quad)
            current_scale = self.zoom_end
        elif elapsed > self.fade_start:
            fade_partial = float(elapsed - self.fade_start) / (self.fade_end - self.fade_start)
            next_opacity = fade_partial
            next_scale = self.zoom_start + self.zoom_amount*fade_partial
            current_opacity = 1-fade_partial
        
        self.current_quad.SetColour( (1,1,1,current_opacity) )
        self.next_quad.SetColour( (1,1,1,next_opacity) )

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
