# -*- coding: utf-8 -*-

try:
    from direct.gui.OnscreenImage import OnscreenImage
    from direct.gui.DirectGui import DirectButton, DirectEntry
    from direct.gui.OnscreenText import OnscreenText
    from direct.showbase.ShowBase import DirectObject
    from panda3d.core import Filename, NodePath, CardMaker, TransparencyAttrib, TextNode, Vec4
    import panda3d
except ModuleNotFoundError:
    print('[Panda3d console]: Failed to import panda3d module')
import sys
import os
import traceback
import importlib
import pathlib
import json
import subprocess
import threading
from direct import showbase
import requests
from .process import py_process, csl_process, cmd_process
from .version import __version__ as version
from .file import BufferFile
from .error import os_error, command_error
from .lines import redistribute, displace, OnscreenLine
from .win_convert import convert
from .defaults import __blacklist__  # change to module names when defined

temp = os.path.dirname(__file__)
PYMAINDIR = str(pathlib.Path(temp).resolve())
MAINDIR = Filename.from_os_specific(PYMAINDIR).getFullpath()  




class Console:
    """
    Constructs and returns a new :class:`Console`.
    """
    def __init__(self):
        '''Main constructor.'''
        # prevent overlapping issues
        base.a2dBottomLeft.set_bin('gui-popup', 0) # base is global and therefore does not need to be imported
        sys.stdout = BufferFile(self._ConsoleOutput)
        sys.stderr = BufferFile(os_error)
        self._res = (base.win.getXSize(), base.win.getYSize(),
                    base.getAspectRatio())
        return None

    
    def create(self, command_dictionary, event: str = "f1", app=None):
        '''Load the settings and set up console Gui elements.
        
        - param `command_dictionary`:     User-specific commands
        - param str `event`:                   (Optional) key pressed to toggle console
        - param <generic class> `app`:         User-specific main application, referred to with keyword `main` in console'''

        # dictionnaries and commands
        defaults = {"usage": self.usage,
                    "help": self.help,
                    "credits": self.credits,
                    "license": self.showLicense}
    
        # append default commands to command dictionnary
        self._command_dictionary = {**command_dictionary, **defaults}
        self._consoles = {
            "csl> ": "Pconsole " + version,
            "pyt> ": sys.version[:5]+" runtime python console",
            "os$> ": "OS commandline"
        }

        # settings
        with open(os.path.join(PYMAINDIR, 'win_symbols.json'), encoding='utf-8') as w_symb:
            self.win_symbols = json.load(w_symb)
        with open(os.path.join(PYMAINDIR, 'config.json')) as config:
            data = json.load(config)
        self._verbose = data['toggleverbose']
        self._bg_transp = data['bg_transparency']
        self._framesize = data['framesize']  # [2 , 2] for fullscreen
        self._disponstartup = data['disponstartup']
        self._minframesize = [0.8, 1]
        self._check_version = data['checkforupdates']
        if self._framesize[0] < self._minframesize[0] or self._framesize[1] < self._minframesize[1]:
            self._framesize = self._minframesize
        # modified framesize according to screen res (most screens aren't square)
        self._resframesize = [self._framesize[0]
            * self._res[2], self._framesize[1]]
        self._hidden = False
        self._textscale = data['textscale']
        self._textres = data['textres']
        self._doresizeroutine = data['doresizeroutine']
        self._doscrollingroutine = data['doscrollingroutine']
        self._font = loader.loadFont(os.path.join(MAINDIR, data['fontpath']))
        self._font.setPixelsPerUnit(self._textres)

        # scrolling
        self._callbackindex = -1
        self._scrollingindex = 0  # start in non-scrolled state
        self._inputlines = [] # this list will contain the recorded lines (for scrolling and resizing purpose)
        self._savedlines = []
        # resizing
        self._recomputeFrame()

        # gui objects
        self._gui = NodePath('GuiNp')
        self._gui.reparentTo(base.a2dBottomLeft)
        _cardmaker = CardMaker('bg')
        _cardmaker.setFrame(-0, self._framesize[0], 0, self._framesize[1])
        _cardmaker.setColor(0, 0, 0, self._bg_transp)
        _cardmaker.set_has_uvs(False)
        _cardmaker.set_has_normals(False)
        self._background = self._gui.attach_new_node(_cardmaker.generate())
        self._background.setTransparency(TransparencyAttrib.MAlpha)\
        # instead of creating the background using the current resolution, we use scaling to adapt its size whenever the user changes the window's size
        self._background.setScale(
            self._resframesize[1]/self._framesize[1], 1, self._resframesize[0]/self._framesize[0])

        self._visible_lines = [OnscreenLine(text='',
                                            pos=(0.01, 0.12 + x *
                                                 self._textscale),
                                            scale=self._textscale,
                                            align=TextNode.ALeft,
                                            fg=(1, 1, 1, 1),
                                            parent=self._gui,
                                            font=self._font,
                                            line=None) for x in range(self._maxlines)]  # the 0 value is the index of the chunk (the actual line)
        self._indicator = DirectButton(text='csl> ',
                                      command=self._switch_adr,
                                      scale=self._textscale,
                                      pos=(0.01, 0, 0.049),
                                      frameColor=(0, 0, 0, 0),
                                      text_font=self._font,
                                      pressEffect=False,
                                      text_fg=(1, 1, 1, 1),
                                      text_align=TextNode.ALeft,
                                      parent=self._gui)
        self._info = OnscreenText(text='targeting: ' + self._consoles[self._indicator['text']],
                                pos=(0.01, 0.01),
                                scale=self._textscale*0.95,
                                align=TextNode.ALeft,
                                fg=(0.7, 0.9, 0.9, 1),
                                parent=self._gui,
                                font=self._font)
        self.__load_console_entry()
        self._update_res()

        # head
        self._ConsoleOutput('Pconsole ' + version, color=Vec4(0.1, 0.1, 1, 1))
        self._ConsoleOutput(
            'Successfully loaded all components', color=Vec4(0, 1, 0, 1))
        self._ConsoleOutput(
            'Type "help", "credits" or "license" for more information.')
        self._ConsoleOutput(
            "Click the prompt keyword or press f2 to change the targeted console")

        # base.buttonThrowers
        self._eventhandler = DirectObject.DirectObject()
        if event == 'f2':
            self._ConsoleOutput(" ")
            self._ConsoleOutput(
                'failed to configure %s key as toggling event, loading default (f1)' % event, Vec4(0.8, 0.8, 1, 1))
            event = 'f1'  # default if conflict with f2
        self._eventhandler.accept(event, self.__toggle)
        self._eventhandler.accept('arrow_up', self._callBack, [True])
        self._eventhandler.accept('arrow_down', self._callBack, [False])
        self._eventhandler.accept('f2', self._switch_adr)
        if self._doscrollingroutine:
            self._eventhandler.accept('wheel_up', self._scroll, [True])
            self._eventhandler.accept('wheel_down', self._scroll, [False])
        if self._doresizeroutine: self._eventhandler.accept(
            'aspectRatioChanged', self._update_res)

        self.app = app
        if self.app == None:
            self._ConsoleOutput(" ")
            self._ConsoleOutput(
                "Warning: 'main' keyword is not available in the python shell, as the 'app' \nargument was not provided")
        if not self._disponstartup: self.__toggle()  # initialize as hidden

        # check for updates in a separate thread
        thread = threading.Thread(target=self._versioncheck, args=())
        thread.daemon = True
        thread.start()

        return None

    def __load_console_entry(self):  # -1.76, 0, -0.97
        '''Load console DirectEntry element.'''
        self.entry = DirectEntry(scale=self._textscale,
                                    frameColor=(0.05, 0.05, 0.05, 0),
                                    text_fg=(1, 1, 1, 1),
                                    pos=(0.1, 0, 0.05),
                                    overflow=1,
                                    command=self.__process,
                                    initialText="",
                                    numLines=1,
                                    focus=True,
                                    width=38,
                                    parent=self._gui,
                                    entryFont=self._font)
        return None

    def __toggle(self):
        '''Toggle console display.'''
        if self._hidden:
            self._gui.show()
        else:
            self._gui.hide()
        self._hidden = not(self._hidden)
        return None

    def __process(self, data):
        """
        Process the data provided by the user and execute the corresponding command.
        """

        if len(data) == 0: return None
        # reset scroll
        self._callbackindex = -1
        # save to scrolling buffer
        self._inputlines.append(data)

        # reset console entry
        self.entry.destroy()
        self.__load_console_entry()
        # 
        self._ConsoleOutput(" ")
        self._ConsoleOutput(self._indicator['text']+data)


        if self._indicator['text'] == 'pyt> ':
            py_process(data, self.app, self._ConsoleOutput)
        elif self._indicator['text'] == 'csl> ':
            csl_process(data, self._ConsoleOutput, self._command_dictionary)
        elif self._indicator['text'] == 'os$> ':
            cmd_process(data, self._ConsoleOutput)
        return None

    def _ConsoleOutput(self, output, color: Vec4 = Vec4(1, 1, 1, 1), mode: str = 'add', CMD_type=False, encoding='utf-8'):
        redistribute(self._savedlines, self._maxsize,
                     self._maxlines, self._visible_lines)

        keyword = "\n"
        if output == None: return
        elif type(output) is bytes: output = convert(output, self.win_symbols)
        if CMD_type: sys.__stdout__.write(output)

        text = output.split(keyword)

        text = [[x[i:i+self._maxsize]
            for i in range(0, len(x), self._maxsize)] for x in text]
        if mode == 'add':
            for discretized in text:
                self._savedlines.append((''.join(discretized), color))
                for i in range(len(discretized)):  # for each line
                    for x in range(self._maxlines-1, 0, -1):
                        self._visible_lines[x].textnode.text = self._visible_lines[x-1].textnode.text
                        self._visible_lines[x].textnode.fg = self._visible_lines[x-1].textnode.fg
                        self._visible_lines[x].lineIndex = self._visible_lines[x-1].lineIndex
                        self._visible_lines[x].charInterval = self._visible_lines[x-1].charInterval
                    self._visible_lines[0].textnode.text = discretized[i]
                    self._visible_lines[0].textnode.fg = color
                    self._visible_lines[0].lineIndex = len(
                        self._savedlines)-1  # save the line number
                    previous = ''
                    # sum up all the previous chars
                    for t in range(i): previous += discretized[t]
                    self._visible_lines[0].charInterval = [
                        len(previous), len(previous)+len(discretized[i])-1]
        elif mode == 'edit':
            # save the line, might not work properly
            self._savedlines[-1] = (output, color)
            for discretized in text:
                n = len(discretized)
                for i in range(n):
                    self._visible_lines[i].textnode.text = discretized[n - i - 1]
                    self._visible_lines[i].textnode.fg = color
                    self._visible_lines[i].lineIndex = len(
                        self._savedlines)-1  # charinterval not handled
        return None

    def _scroll(self, direction: bool):
        sign = (-1)**int(direction+1)  # -1 or 1 depending on the boolean
        self._scrollingindex = displace(
            self._savedlines, self._maxsize, self._maxlines, self._visible_lines, self._scrollingindex, sign)

    def _switch_adr(self):
        current = self._indicator['text']
        n = list(self._consoles.keys()).index(current)
        if n == len(self._consoles.keys())-1:
            n = 0
        else:
            n += 1
        self._indicator['text'] = list(self._consoles.keys())[n]
        self._info.text = "targeting: " + \
            self._consoles[self._indicator['text']]

    def _update_res(self):
        self._res = (base.win.getXSize(), base.win.getYSize(),
                    base.getAspectRatio())  # update res
        # update frame stuff
        # if self._maxsize < 10: return # we want the indicator to always stay inside the background frame
        self._resframesize = [self._framesize[0]
            * self._res[2], self._framesize[1]]
        self._recomputeFrame()
        self._background.setScale(
            self._resframesize[0]/self._framesize[0], 1, self._resframesize[1]/self._framesize[1])
        # update text disposition
        redistribute(self._savedlines, self._maxsize,
                     self._maxlines, self._visible_lines)
        self._scrollingindex = 0  # reset scrolling
        self.entry['width'] = self._maxsize
        # debug
        if self._verbose: print('updated res to %s - x,y,ratio' % str(
            (base.win.getXSize(), base.win.getYSize(), base.getAspectRatio())))

    def _callBack(self, key: bool):
        invertedInput = self._inputlines[::-1]
        if key:  # up key pressed
            try:  # avoid out of range errors
                if self._callbackindex < len(invertedInput):
                    self._callbackindex += 1
                    self.entry.enterText(invertedInput[self._callbackindex])
            except: pass
        else:
            try:
                if self._callbackindex >= 0:
                    self._callbackindex -= 1
                    self.entry.enterText(
                        ([''] + invertedInput)[self._callbackindex])
            except: pass

    def _textToLine(self, text):
        try:
            text = text.replace("\n", "")
        except:
            pass
        return text

    def _recomputeFrame(self):
        def getfontbounds():
            nonlocal self
            temp = OnscreenText(text='1234567890', scale=self._textscale)
            bounds = temp.getTightBounds()
            temp.destroy()
            return bounds
        bounds = getfontbounds()
        width = (bounds[1][0] - bounds[0][0])/10
        self._maxsize = int(self._resframesize[0]/width)
        self._maxlines = int((self._resframesize[1]-0.12)/self._textscale) + 1

    def _versioncheck(self):
        # version_check
        if not self._check_version: return
        self._ConsoleOutput(" \nChecking for updates...", Vec4(0.8, 0.7, 0, 1))
        try:
            # load project json
            r = requests.get("https://pypi.org/pypi/pconsole/json")
            # load last version available (str format)
            latest = list(r.json()['releases'].keys())[-1]
        except:
            self._ConsoleOutput("failed to connect to the Pypi database via json protocol\n ", Vec4(0.8,0.7,0,1))
            return

        if latest != version and int(''.join(version.split('.'))) < int(''.join(latest.split('.'))):
            self._ConsoleOutput("This version of pconsole ({}) is outdated.\nPlease consider updating it using the command 'pip install pconsole'\n ".format(
                version), Vec4(0.8, 0.7, 0, 1))
        elif int(''.join(version.split('.'))) > int(''.join(latest.split('.'))):
            self._ConsoleOutput("This version of pconsole ({}) hasn't been released yet.\nIt may therefore contain some bugs.\nPlease consider installing a stable build using \n'pip install pconsole'\n ".format(version), Vec4(0.8,0.7,0,1))
        else:
            self._ConsoleOutput("This version of pconsole is currently up-to-date", Vec4(0.8,0.7,0,1))
        
        
    def usage(self,index):
        '''
        Provides help concerning a given command
        '''
        try:
            i = self._command_dictionary[index]
            self._ConsoleOutput("Help concerning command '%s':" % str(index), color = (0.243,0.941,1,1))
            self._ConsoleOutput("- associated function name is '%s'" % str(i.__name__))
            self._ConsoleOutput("- Documentation provided: ")
            doc = self._textToLine(str(i.__doc__))
            if not doc == str(None):
                self._ConsoleOutput(doc.strip())
            else:
                self._ConsoleOutput("No docstring found")
            self._ConsoleOutput("- Known arguments: ")
            
            arg = list(i.__code__.co_varnames)
            # del arg[0] # remove the self argument
            arg = str(arg)
            if len(arg)-2:
                self._ConsoleOutput(str(arg)[1:len(str(arg))-1]) # remove brackets
            else:
                self._ConsoleOutput("No arguments required")
        except KeyError: # not in the dictionary
            self._ConsoleOutput("Unknown command '%s'" % str(index), (1,0,0,1))
        return None
    
    def help(self):
        '''
        Shows a list of available commands
        '''
        self._ConsoleOutput("List of available commands: ", color = (0.243,0.941,1,1))
        for i in self._command_dictionary:
            self._ConsoleOutput("- "+str(i))
        self._ConsoleOutput(" ")
        self._ConsoleOutput("Use usage(command) for more details on a specific command")
        return None

    def credits(self):
        self._ConsoleOutput("Thanks to rdb, darthrigg, and the panda3d community for supporting this project.")
        self._ConsoleOutput("This program was created by l3alr0g. See https://github.com/l3alr0g/pconsole for more information.")
        self._ConsoleOutput("Download the panda3d engine at panda3d.org")

    def showLicense(self):
        with open(os.path.join(PYMAINDIR,'license.txt')) as l:
            license = l.read()
        self._ConsoleOutput(license, color = (1, 0.9, 0.7, 1))

def find_all_str(sample, string):
    n = len(sample)
    poslist = []
    for i in range(len(string)-n+1):
        if string[i:i+n] == sample:
            poslist.append(i)
        else:pass
    return poslist
