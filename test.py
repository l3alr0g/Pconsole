import pconsole
from panda3d.core import Filename
from direct.showbase.ShowBase import ShowBase
from direct.gui.OnscreenImage import OnscreenImage
from threading import Thread
import os,sys

MAINDIR = Filename.from_os_specific(os.path.abspath(sys.path[0])).getFullpath()

class TestApp(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        self.disable_mouse()
        self.mire = OnscreenImage(image = os.path.join(MAINDIR,'test.jpeg'))
        self.mire.setScale(1.6, 1, 1)
        self.mire.hide()
        self.is_shown = False
        
        command_dic = {
            "toggleImage":self.toggleImage
        }
        self.commandline = pconsole.Console()
        self.commandline.create(command_dic, app = self, event = 'f1')
        self.task_mgr.add(self.update, "updatingTask")
        
        
    def update(self, task):
        return task.cont
    
    def toggleImage(self):
        if self.is_shown:
            self.mire.hide()
        else:
            self.mire.show()
        self.is_shown = not self.is_shown

def testfunc():
    '''docstring goes here'''
    pass

App = TestApp()
App.run()
