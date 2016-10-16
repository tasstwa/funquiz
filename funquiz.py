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

default_config = {
                    "rounds": 5,
                    "teams": [ "Equipe %d" % (i,) for i in range(1,3) ],
                    "players": [ (int(round(i/4)),"Joueur #%d" % (i+1,)) for i in range(8)]
                } 

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
                   "NoAnswer",
                   "Winners"
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
        self.add_transition('go','Test','AskQuestion')
        self.add_transition('hitBuzzer','Test','Test',before=['store_buzzer_status'])
 #       self.add_transition('tick','Test','Test',before=['store_buttons'])
        # AskQuestion
        self.add_transition('keypress','AskQuestion','WaitAnswer')
        self.add_transition('tick',"AskQuestion","Winners",conditions="done")

        # WaitAnswer
        self.add_transition('hitBuzzer','WaitAnswer','WaitJudge')
        self.add_transition('tick','WaitAnswer','Countdown',after=['display_time_left'])
#        self.add_transition('keypress','WaitAnswer','WaitJudge',conditions='is_buzzer_key')
        # Countdown
        self.add_transition('hitBuzzer','Countdown','WaitJudge',before=['store_who_answered'])
        self.add_transition('one_second','Countdown','Countdown',before=['dec_timer','display_time_left'])
        self.add_transition('time_expired',"Countdown","NoAnswer")
        # NoAnswer
        self.add_transition('keypress',"NoAnswer","AskQuestion")
       
        # WaitJudge
        self.add_transition('yes','WaitJudge','RightAnswer')
        self.add_transition('no','WaitJudge','WrongAnswer')

        # RightAnswer
        self.add_transition('keypress',"RightAnswer","AskQuestion")

        # WrongAnswer
        self.add_transition('keypress',"WrongAnswer","AskQuestion")

        self.read_config()
        self.round = 0
        self.score = [ 0, 0 ]
        self.buttons = [ False ] * 8 # Local copy of pressed buttons
        self.screen = Screen()
        self.to_Welcome()

    def read_config(self):
        try:
            self.config = json.load(file("funquiz.cfg"))
        except IOError:
            self.config = default_config
        self.players = self.config["players"]

    def after_state_change(self,event):
        self.screen.set_status("Ronde %2u/%2u  %s: %2u   %s: %2u" % 
            (self.round,self.config["rounds"],self.config["teams"][0],self.score[0],self.config["teams"][1],self.score[1]))
        self.screen.set_title( self.state)
        
    def done(self,event):
        return self.round > self.config["rounds"]
 
    def never(self,event):
        return False
    def store_buttons(self,event):
        self.buttons = event.kwargs['buttons']
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
            self.screen.addstr(5 + i,5,"%s [%s]" % (self.players[i][1],s))
    def store_buzzer_status(self,event):
        index = int(event.kwargs['num'])
        self.buzzer_tested[index] = True
        self.buttons = event.kwargs['buttons']
    def on_enter_AskQuestion(self,event):
        self.answered_by = None
        self.round += 1
        self.screen.clear()
        self.screen.addstr(4,3,"Posez la question. Pressez une touche pour attendre la reponse")
        self.screen.addstr(5,3,"et commencer le compte a rebours.")
    def on_enter_WaitAnswer(self,event):
        self.screen.clear()
        self.screen.addstr(4,3,"On attends la reponse...")
        self.countdown = 5
    def dec_timer(self,event):
        self.countdown -= 1
    def display_time_left(self,event):
        self.screen.addstr(5,6,"%d sec" % self.countdown)
        if self.countdown <= 0:
            self.time_expired()
    def store_who_answered(self,event):
        player = event.kwargs.get('num',None)
        self.answered_by = int(player)
        
    def on_enter_NoAnswer(self,event):
        self.screen.clear()
        self.screen.addstr(4,3,"Pas de reponse. On continue... pressez une touche.")
        
    def on_enter_WaitJudge(self,event):
        player = event.kwargs.get('num',None)
        self.screen.clear()
        self.screen.addstr(4,3,"'%s' a ete le plus vite.\n" % (self.players[int(player)][1],)) 
        self.screen.addstr(5,3,"La reponse est bonne? (O/N)")
         
    def on_enter_RightAnswer(self,event):
        self.screen.clear()
        winning_team = self.players[self.answered_by][0]

        self.screen.addstr(4,3,"Bonne reponse par %s [%s]! On continue... pressez une touche." %
                 (self.players[self.answered_by][1],self.config["teams"][winning_team]))
        self.score[winning_team] += 1

    def on_enter_WrongAnswer(self,event):
        self.screen.clear()
        losing_team = self.players[self.answered_by][0]
        self.screen.addstr(4,3,"Mauvaise reponse par %s [%s]! On continue... pressez une touche." %
                 (self.players[self.answered_by][1],self.config["teams"][losing_team]))
    def on_enter_Winners(self,event):
        self.screen.clear()
        winner = "Aucune!"
        if self.score[0] > self.score[1]:
            winner = self.config["teams"][0]
        elif self.score[1] > self.score[0]:
            winner = self.config["teams"][1]
    
        self.screen.addstr(4,3,"Equipe gagnante: %s... " % winner)
        self.screen.addstr(5,3,"Taper ESC pour quitter")
        

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
    def set_status(self,status):
        self.status_line = status
    def set_title(self,title):
        s = '[' + title + ' ' * (32-len(str(title))) + ']'
        self.status.clear()
        self.status.addstr(0,3,s)
        self.status.addstr(1,3,self.status_line)
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
    special_keys = {
            'o': machine.yes,
            'n': machine.no,
            'g': machine.go
            }
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
                if chr(ch) in special_keys.keys():
                    special_keys[chr(ch)](key=ch,buttons=button_pressed)

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
