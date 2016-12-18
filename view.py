from OpenGL.GL import *
import random,numpy,cmath,math,pygame

import ui,globals,drawing,os,copy
from globals.types import Point
import random

class PlayerData(ui.UIElement):
    margin = Point(0,0.1)
    unselected = (0, 0, 0.4, 1.0)
    selected = (1, 0.5, 0, 1)
    def __init__(self, parent, pos, tr, name):
        if not name:
            name = 'unknown'
        self.name = name
        super(PlayerData, self).__init__( parent, pos, tr )
        self.box = ui.Box(self, Point(0,self.margin.y), Point(1,1.0 - self.margin.y), colour=self.unselected)
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

    def select(self):
        self.box.SetColour(self.selected)
        self.text.SetColour(self.unselected)

    def unselect(self):
        self.box.SetColour(self.unselected)
        self.text.SetColour(self.selected)

    def Destroy(self):
        self.box.Delete()
        

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
        self.set_items(['Fiz Gig','Tallin Erris','Brottor Strakeln','Cirefus'], 0)

    def set_items(self, name_list, chosen):
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

        self.chosen = chosen
        self.items[chosen].select()
        
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

