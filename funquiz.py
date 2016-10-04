from __future__ import print_function
import os
import curses
import pygame
import sys
import json
import transitions
import logging

class Game(transitions.Machine):
    def __init__(self):
        states = [ "Welcome",
                   "Setup",
                   "AskQuestion",
                   "WaitAnswer",
                   "RightAnswer",
                   "WrongAnswer",
                   "StealAnswer",
                   "Timeout",
                   "Score"
                 ]
        transitions.Machine.__init__(self,states=states,initial="Welcome",send_event=True,ignore_invalid_triggers=True,queued=True)
        self.add_transition('keypress','Welcome','Setup')
        self.add_transition('enter','Setup','Welcome')
        self.add_transition('tick','WaitAnswer','Timeout')
        self.round = 0

class Screen(object):
    def __init__(self):
        self.window = curses.initscr()
        curses.cbreak()
        curses.halfdelay(1)
        self.window.border()
    def getch(self):
        return self.window.getch()
    def cleanup(self):
        curses.endwin()

def feed_events(machine):
    screen = Screen()
    try:
        while True:
            ch = screen.getch()
            if ch == curses.ERR:
                machine.tick()
            elif ch == curses.ascii.ESC:
                break
            else:
                machine.keypress(ch)
    except:
        raise
    finally:
        screen.cleanup()   
        

def main():
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    transitions.logger.setLevel(logging.DEBUG)
    game = Game()
    feed_events(game)
    

if __name__ == "__main__":
    main()
    
