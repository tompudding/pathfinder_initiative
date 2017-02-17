import os, sys
import pygame
import ui
import globals
import drawing
import view
import time
import socket
import threading
import SocketServer
from globals.types import Point
import messages

def Init():
    """Initialise everything. Run once on startup"""
    w,h = (1920,1080)
    globals.tile_scale            = Point(1,1)
    globals.scale                 = Point(1,1)
    globals.screen_abs            = Point(w,h)
    globals.screen                = globals.screen_abs/globals.scale
    globals.screen_root           = ui.UIRoot(Point(0,0),globals.screen_abs)
    globals.mouse_screen          = Point(0,0)

    globals.quad_buffer           = drawing.QuadBuffer(131072)
    globals.screen_texture_buffer = drawing.QuadBuffer(131072, ui=True)
    globals.ui_buffer             = drawing.QuadBuffer(131072, ui=True)
    globals.nonstatic_text_buffer = drawing.QuadBuffer(131072, ui=True)
    globals.colour_tiles          = drawing.QuadBuffer(131072)
    globals.mouse_relative_buffer = drawing.QuadBuffer(1024, ui=True, mouse_relative=True)
    globals.line_buffer           = drawing.LineBuffer(16384)
    globals.tile_dimensions       = Point(16,16)*globals.tile_scale
    globals.zoom_scale            = None
    globals.time_step             = 0.05
    globals.processing            = False

    globals.dirs = globals.types.Directories('resource')

    pygame.init()
    screen = pygame.display.set_mode((w,h),pygame.OPENGL|pygame.DOUBLEBUF)
    pygame.display.set_caption('Pathfinder')

    drawing.Init(globals.screen.x,globals.screen.y)
    pygame.mouse.set_visible(False)
    globals.text_manager = drawing.texture.TextManager()

class ThreadedTCPRequestHandler(SocketServer.BaseRequestHandler):
    def handle(self):
        data = self.request.recv(1024)
        #First there should be a single byte which is the selected number
        if not data:
            return
        message_type = ord(data[0])
        print 'Got message %d' % message_type
        if message_type == messages.MessageType.REQUEST_IMAGE_LIST:
            #This means request image list
            print 'Sending list',globals.environ_list
            self.request.send('\x00'.join(globals.environ_list))
        elif message_type == messages.MessageType.CHOOSE_IMAGE_LIST:
            #This mean choose image list
            name = data[1:].split('\x00')[0]
            new_event = pygame.event.Event(pygame.USEREVENT + 1, {'name' : name})
            pygame.event.post(new_event)

        elif message_type == messages.MessageType.GAME_MODE:
            if globals.processing:
                return
            globals.processing = True
            chosen = ord(data[1])
            gone = ord(data[2])
            names = data[3:].split('\x00')
            print 'got',names,chosen
            new_event = pygame.event.Event(pygame.USEREVENT, {'names' : names, 'chosen' : chosen, 'gone' : gone })
            pygame.event.post(new_event)


class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    allow_reuse_address = True

def main():
    """Main loop for the game"""
    Init()

    server = ThreadedTCPServer(('0.0.0.0', 4919), ThreadedTCPRequestHandler)
    ip, port = server.server_address

    globals.environ_list = os.listdir('resource')
    print globals.environ_list

    # Start a thread with the server -- that thread will then start one
    # more thread for each request
    server_thread = threading.Thread(target=server.serve_forever)
    # Exit the server thread when the main thread terminates
    server_thread.daemon = True
    server_thread.start()
    print "Server loop running in thread:", server_thread.name

    globals.game_view = view.GameView()
    globals.image_view = view.ImageView()

    #Start with a neutral image being displayed
    globals.view = globals.image_view

    done = False
    last = 0
    clock = pygame.time.Clock()
    drawing.InitDrawing()
    #pygame.display.toggle_fullscreen()

    while not done:
        clock.tick(30)
        globals.time = pygame.time.get_ticks()
        
        drawing.NewFrame()
        globals.image_view.Update()
        globals.image_view.Draw()
        globals.game_view.Update()
        globals.game_view.Draw()
        globals.screen_root.Draw()
        globals.text_manager.Draw()
        #drawing.EndFrame()
        pygame.display.flip()

        eventlist = pygame.event.get()
        for event in eventlist:
            if event.type == pygame.locals.QUIT:
                done = True
                break
            elif (event.type == pygame.KEYUP):
                if event.key == pygame.K_f:
                    pygame.display.toggle_fullscreen()

            elif event.type == pygame.USEREVENT:
                #if globals.view is not globals.game_view:
                #    globals.view.hide()
                #    globals.view = globals.game_view
                globals.game_view.set_items(event.names, event.chosen, event.gone)
                globals.image_view.set_colour( (0.5,0.5,0.5) )
                globals.processing = False

            elif event.type == pygame.USEREVENT + 1:
                #if globals.view is not globals.image_view:
                #    globals.view.hide()
                #    globals.view = globals.image_view
                globals.game_view.clear_items()
                globals.image_view.set_dir(event.name)
                globals.image_view.set_colour( (1,1,1) )


if __name__ == '__main__':
    import logging
    try:
        logging.basicConfig(level=logging.DEBUG, filename='errorlog.log')
        #logging.basicConfig(level=logging.DEBUG)
    except IOError:
        #pants, can't write to the current directory, try using a tempfile
        pass

    try:
        main()
    except Exception, e:
        print 'Caught exception, writing to error log...'
        logging.exception("Oops:")
        #Print it to the console too...
        raise
