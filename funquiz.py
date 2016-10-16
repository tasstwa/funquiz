# vim: set fileencoding=utf8 :
from __future__ import print_function
import os
import curses,curses.ascii
import pygame
import sys
import json
import transitions
import logging
import time

class Game(transitions.Machine):
    def __init__(self):
        states = [ "Start",
                   "Welcome",
                   "Test",
                   "AskQuestion",
                   "WaitAnswer",
                   "Countdown",
                   "WaitJudge",
                   "RightAnswer",
                   "WrongAnswer",
                   "StealAnswer",
                   "NoAnswer",
                   "Score"
                 ]
        transitions.Machine.__init__(self,
                states=states,
                initial="Start",
                send_event=True,
                ignore_invalid_triggers=True,
                after_state_change=self.after_state_change,
                queued=True)
        self.add_transition('tick','Test','Timeout',conditions=[ "never" ])
        # Welcome
        self.add_transition('keypress','Welcome','Test')
        # Test
        self.add_transition('keypress','Test','AskQuestion',conditions='ready_to_go')
        self.add_transition('hitBuzzer','Test','Test',before=['store_buzzer_status'])
 #       self.add_transition('tick','Test','Test',before=['store_buttons'])
        # AskQuestion
        self.add_transition('keypress','AskQuestion','WaitAnswer')
        # WaitAnswer
        self.add_transition('hitBuzzer','WaitAnswer','WaitJudge')
        self.add_transition('tick','WaitAnswer','Countdown')
#        self.add_transition('keypress','WaitAnswer','WaitJudge',conditions='is_buzzer_key')
        # Countdown
        self.add_transition('hitBuzzer','Countdown','WaitJudge')
        self.add_transition('one_second','Countdown','Countdown',before=['display_time_left'])
        self.add_transition('time_expired',"Countdown","NoAnswer")

        self.round = 0
        self.buttons = [ False ] * 8 # Local copy of pressed buttons
        self.screen = Screen()
        self.to_Welcome()

    def after_state_change(self,event):
        self.screen.set_title( self.state)
        
    def never(self,event):
        return False
    def store_buttons(self,event):
        self.buttons = event.kwargs['buttons']
    def ready_to_go(self,event):
        return event.kwargs.get('key',0) == ord('g')
    def is_buzzer_key(self,event):
        ch = event.kwargs.get('key',0)
        return ch >= ord('1') and ch <= ord('8')
    def on_enter_Welcome(self,event):
        self.buzzer_tested = [ False ] * 8
    def on_enter_Test(self,event):
        self.screen.addstr(4,3,"Tout les joueurs active leurs buzzers. Faire 'g' quand pret.")
        for i in range(len(self.buzzer_tested)):
            s = { True: "OK" , False: "__"}[self.buzzer_tested[i]] 
       #     s = { True: "OK" , False: "  "}[self.buttons[i]] 
            self.screen.addstr(5 + i,5,"Joueur #%d [%s]" % (i+1,s))
    def store_buzzer_status(self,event):
        index = int(event.kwargs['num'])
        self.buzzer_tested[index] = True
        self.buttons = event.kwargs['buttons']
    def on_enter_AskQuestion(self,event):
        self.screen.clear()
        self.screen.addstr(4,3,"Posez la question. Pressez une touche pour attendre la reponse")
        self.screen.addstr(5,3,"et commencer le compte a rebours.")
    def on_enter_WaitAnswer(self,event):
        self.screen.clear()
        self.screen.addstr(4,3,"On attends la reponse...")
        self.countdown = 5
    def display_time_left(self,event):
        self.countdown -= 1
        self.screen.addstr(5,6,"%d sec" % self.countdown)
        if self.countdown <= 0:
            self.time_expired()
        
    def on_enter_WaitJudge(self,event):
        player = event.kwargs.get('num',None)
        self.screen.clear()
        self.screen.addstr(4,3,"Joueur #%d doit a ete le plus vite." % (player,)) 
         

class Screen(object):
    def __init__(self):
        self.stdscr = curses.initscr()
        self.max_y,self.max_x = self.stdscr.getmaxyx()
        curses.start_color()
        curses.use_default_colors()
        curses.cbreak()
        curses.noecho()
        curses.halfdelay(1)
        self.stdscr.border()
        self.stdscr.refresh()
        self.window = curses.newwin(self.max_y-7,self.max_x-2,6,1)
        self.clear()
        self.status =  curses.newwin(5,self.max_x-2,1,1)
        self.status.refresh()
        self.window.border()
        self.window.refresh()
    def getch(self):
        return self.window.getch()
    def cleanup(self):
        curses.endwin()
    def set_title(self,title):
        s = '[' + title + ' ' * (32-len(str(title))) + ']'
        self.status.clear()
        self.status.addstr(0,3,s)
        self.status.refresh()
    def addstr(self,*args):
        self.window.addstr(*args)
        self.window.refresh()
    def clear(self):
        self.window.clear()
        self.window.border()
        self.window.refresh()


def feed_events(machine):
    button_pressed = [ False ] * 8
    fake_button_on = [ 0 ] * 8
    screen = machine.screen
    try:
        one_second = time.time()
        while True:
            ch = screen.getch()
            now = time.time()
            if (now - one_second) > 1.0:
                machine.one_second(buttons=button_pressed)
                one_second = now
            if ch == curses.ERR:
                for i in range(len(fake_button_on)):
                    if fake_button_on[i] == 1:
                        button_pressed[i] = False
                    if fake_button_on[i] > 0:
                        fake_button_on[i] -= 1

                machine.tick(buttons=button_pressed)
                
            elif ch == curses.ascii.ESC:
                break
            # Simulate a 1s press with keys 1-8
            elif ch >= ord('1') and ch <= ord('8'):
                index = ch - ord('1')
                fake_button_on[index] = 10
                button_pressed[index] = True
                machine.hitBuzzer(num = index,buttons=button_pressed)
            else:
                machine.keypress(key=ch,buttons=button_pressed)
    except:
        raise
    finally:
        screen.cleanup()   
        

def main():
    logging.basicConfig(stream=file("funquiz.log","w"), level=logging.INFO)
    transitions.logger.setLevel(logging.DEBUG)
    game = Game()
    feed_events(game)
    

if __name__ == "__main__":
    main()
    
