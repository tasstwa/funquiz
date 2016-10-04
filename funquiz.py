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
        self.round = 0


def main():
    transitions.logger.setLevel(logging.DEBUG)
    game = Game()
    print game.state
    game.keypress()
    print game.state
    game.enter()
    print game.state

    

if __name__ == "__main__":
    main()
    
