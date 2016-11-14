# vim: set fileencoding=utf8 :
from __future__ import print_function
import os
import math
import os.path
import curses,curses.ascii
import pygame
import sys
import json
import transitions
import logging
import time

try:
    import RPi.GPIO as GPIO
except RuntimeError:
    print("Need root access")


default_config = {
                    "rounds": 5,
                    "teams": [ "Equipe %d" % (i,) for i in range(1,3) ],
                    "players": [ (int(round(i/4)),"Joueur #%d" % (i+1,)) for i in range(8)],
                    "answer_timeout": 5
                } 

class Game(transitions.Machine):
    states = { "Start" : None,
           "Welcome": None,
           "Test": "Verifier vos temoins",
           "AskQuestion": "Attention:",
           "WaitAnswer": None,
           "Countdown":"Reponse SVP",
           "WaitJudge": None,
           "RightAnswer": "Bravo!",
           "WrongAnswer": "Mauvaise reponse",
           "NoAnswer": "Trop tard!",
           "Steal": "Droit de reponse",
           "WaitJudgeSteal": None,
           "Winners": None
         }
    def __init__(self):
        transitions.Machine.__init__(self,
                states=Game.states.keys(),
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
        self.add_transition('hitBuzzer','Test','Test',conditions=['store_buzzer_status'])
        self.add_transition('tick','Test','Test',conditions=['display_buttons'])
        # AskQuestion
        self.add_transition('keypress','AskQuestion','WaitAnswer')
        self.add_transition('tick',"AskQuestion","Winners",conditions="done")
        self.add_transition('screenDone',"AskQuestion","AskQuestion",prepare=["show_score"],conditions="never")

        # WaitAnswer
        self.add_transition('hitBuzzer','WaitAnswer','WaitJudge')
        self.add_transition('tick','WaitAnswer','Countdown',after=['display_time_left'])
#        self.add_transition('keypress','WaitAnswer','WaitJudge',conditions='is_buzzer_key')
        # Countdown
        self.add_transition('hitBuzzer','Countdown','WaitJudge',prepare=['store_who_answered'])
        self.add_transition('one_second','Countdown','Countdown',prepare=['display_time_left'],conditions="never")
        self.add_transition('tick',"Countdown","Countdown",prepare=["dec_timer","display_graphic_countdown"],conditions="never")
        self.add_transition('time_expired',"Countdown","NoAnswer")
        # NoAnswer
        self.add_transition('keypress',"NoAnswer","AskQuestion")
       
        # WaitJudge
        self.add_transition('yes','WaitJudge','RightAnswer')
        self.add_transition('no','WaitJudge','WrongAnswer')

        # RightAnswer
        self.add_transition('keypress',"RightAnswer","AskQuestion")

        # WrongAnswer
        self.add_transition('keypress',"WrongAnswer","Steal")
        
        # Steal
        self.add_transition('hitBuzzer','Steal','WaitJudgeSteal',after=['store_who_answered'],conditions=['limit_steal_team'])
        self.add_transition('one_second','Steal','Steal',prepare=['display_time_left'],conditions="never")
        self.add_transition('tick',"Steal","Steal",prepare=["dec_timer","display_graphic_countdown"],conditions="never")
        self.add_transition('time_expired',"Steal","NoAnswer")

        # WaitJudgeSteal
        self.add_transition('yes','WaitJudgeSteal','RightAnswer')
        self.add_transition('no','WaitJudgeSteal','AskQuestion')

        self.read_config()
        self.round = 0
        self.score = [ 0, 0 ]
        self.buttons = [ False ] * 8 # Local copy of pressed buttons
        self.screen = Screen()
        self.candy = Candy()
        self._load_images()
        self.to_Welcome()

    def _load_images(self):
        img = [ ("Welcome", "bienvenue.jpg"),
                ("Test", "space_shuttle.jpg"),
                ("AskQuestion", "listen.jpg"),
                ("Countdown", "button.png"),
                ("RightAnswer","success.png"),
                ("WrongAnswer","failure.png"),
                ("NoAnswer","clock.jpg"),
                ("Steal","steal.png"),
            ]
        self.imgs = {}
        for handle,filename in img:
            if filename != None:
                self.imgs[handle] = self.candy.get_image_obj(os.path.join("media",filename))

    def read_config(self):
        try:
            with file("funquiz.cfg") as fd:
                self.config = json.load(fd)
        except IOError:
            self.config = default_config
        self.players = self.config["players"]

    def after_state_change(self,event):
        self.screen.set_status("Ronde %2u/%2u  %s: %2u   %s: %2u" % 
            (self.round,self.config["rounds"],self.config["teams"][0],self.score[0],self.config["teams"][1],self.score[1]))
        self.screen.set_title( self.state)
        if self.state in self.imgs.keys():
            self.candy.show_image(self.imgs[self.state],Game.states[self.state])
        self.screenDone() 
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
        self.display_test_result()

    def display_test_result(self):
        for i in range(len(self.buzzer_tested)):
            s = { True: "OK" , False: "__"}[self.buzzer_tested[i]] 
       #     s = { True: "OK" , False: "  "}[self.buttons[i]] 
            self.screen.addstr(5 + i,5,"%s [%s]" % (self.players[i][1],s))

    def store_buzzer_status(self,event):
        index = int(event.kwargs['num'])
        self.buzzer_tested[index] = True
        self.buttons = event.kwargs['buttons']
        self.display_test_result()
        return False
    def display_buttons(self,event):
        self.candy.show_buttons(self.buttons,[ x[1] for x in self.players])
        return False

    def on_enter_AskQuestion(self,event):
        self.answered_by = None
        self.answer_value = 2
        self.round += 1
        self.screen.clear()
        self.screen.addstr(4,3,"Posez la question. Pressez une touche pour attendre la reponse")
        self.screen.addstr(5,3,"et commencer le compte a rebours.")
    def show_score(self,event):
        self.candy.display_text([ "%s: %u" % ( self.config["teams"][t], self.score[t]) for t in range(2) ],(0,240,20))

    def on_enter_WaitAnswer(self,event):
        self.screen.clear()
        self.screen.addstr(4,3,"On attends la reponse...")
        self.ds_left = self.config["answer_timeout"] * 10   # Tick is 1/10s
    def dec_timer(self,event):
        if (self.ds_left % 10) == 0:
            pass
        #            self.one_second(event)
        self.ds_left -= 1
        self.display_time_left(event)
    def display_time_left(self,event):
        self.screen.addstr(5,6,"%d sec" % int(self.ds_left/10.0+1))
        if self.ds_left <= 0:
            self.time_expired()
    def display_graphic_countdown(self,event):
        color = (220,10,10)
        self.candy.show_progress(100.0*self.ds_left/(10.0 * self.config["answer_timeout"]),color,str(int(self.ds_left/10)))

    def limit_steal_team(self,event):
        player = event.kwargs.get('num',None)
        stole_by = int(player)
        return self.players[stole_by][0] != self.players[self.answered_by][0] 
 
    def store_who_answered(self,event):
        player = event.kwargs.get('num',None)
        self.answered_by = int(player)
        self.buttons = [False] * 8
        self.buttons[self.answered_by] = True
        self.candy.show_buttons(self.buttons,[ x[1] for x in self.players])
        
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
        self.score[winning_team] += self.answer_value

    def on_enter_WrongAnswer(self,event):
        self.screen.clear()
        losing_team = self.players[self.answered_by][0]
        self.screen.addstr(4,3,"Mauvaise reponse par %s [%s]! On continue... pressez une touche." %
                 (self.players[self.answered_by][1],self.config["teams"][losing_team]))

    def on_enter_Steal(self,event):
        self.answer_value = 1
        self.ds_left = self.config["answer_timeout"] * 10   # Tick is 1/10s
        self.screen.clear()
        self.screen.addstr(4,3,"Posez la question. Pressez une touche pour attendre la reponse")
        self.screen.addstr(5,3,"et commencer le compte a rebours.")

    def on_enter_WaitJudgeSteal(self,event):
        return self.on_enter_WaitJudge(event)
        
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

class Candy(object):
    """ Eye Candy"""
    def __init__(self):
        pygame.init()
        if len(sys.argv) > 1 and sys.argv[1] == "-f":
            size=(1200,1080)
            self.screen = pygame.display.set_mode(size,pygame.FULLSCREEN)
        else:
            size=(700,500)
            self.screen = pygame.display.set_mode(size)
        self.font = pygame.font.Font(os.path.join("font","BebasNeue.otf"),120)
        self.player_font = pygame.font.Font(os.path.join("font","BebasNeue.otf"),60)
        self.text_cache = {}
        self.background = None
        pygame.display.update()
    def show_image(self,iobj,text=None,color=(0,0,0),sound=None):
        self.screen.blit(iobj,(0,0))
        if text != None:
            if (text,color) in self.text_cache.keys():
                txt = self.text_cache[(text,color)]
            else:
                txt = self.font.render(text,True,color)
                self.text_cache[(text,color)] = txt
            sx,sy = txt.get_size()
            posx = self.screen.get_width()/2 - sx/2
            posy = self.screen.get_height() * 0.1
            self.screen.blit(txt,(posx,posy))

        self.background = self.screen.copy()
        pygame.display.update()

    def get_image_obj(self,filename):
        obj = pygame.image.load(filename).convert()
        return pygame.transform.scale(obj,self.screen.get_size())

    def show_buttons(self,button_pressed_list,button_names):
        # Display two columns per team
        self.screen.blit(self.background,(0,0))
        team1x,team1y = (20,self.screen.get_height() * 0.3)
        team2x,team2y = (self.screen.get_width() * 0.55,team1y)
        for i in range(len(button_names)/2):
            if button_pressed_list[i]:
                txt = self.player_font.render(button_names[i],True,(0xff,0xee,0x52))
                self.screen.blit(txt,(team1x,team1y))
            if button_pressed_list[i+4]:
                txt = self.player_font.render(button_names[i+4],True,(0x52,0x63,0xff))
                self.screen.blit(txt,(team2x,team2y))
            team1y += self.player_font.get_height() + 10
            team2y += self.player_font.get_height() + 10
        pygame.display.update()
    def show_progress(self,percent,color=(0,0,0),text=None):
        self.screen.blit(self.background,(0,0))

        xpos = self.screen.get_width()*0.8
        ypos = self.screen.get_height()*0.2
        xsize = 50
        ysize = self.screen.get_height()*0.7
        black=(0,0,0)
        thick = 2
        pygame.draw.rect(self.screen,black,(xpos,ypos,xsize,ysize),thick+1)
        # Adjust to display
        xpos += thick
        xsize -= thick*2
        ysize -= thick*2
        ypos = ypos + ysize * (100.0 - percent)/100.0
        ysize = ysize * percent/100.0
        pygame.draw.rect(self.screen,color,(xpos,ypos,xsize,ysize),0) 
        pygame.display.update()

    def display_text(self,list_of_text,color=(0,0,0)):
        xpos = self.screen.get_width()* 0.1
        ypos = self.screen.get_height() * 0.35
        for line in list_of_text:
            txt = self.player_font.render(line,True,color)
            self.screen.blit(txt,(xpos,ypos))
            ypos += self.player_font.get_height() + 10
        pygame.display.update()

    def cleanup(self):
        pygame.quit()


def feed_events(machine):
    button_pressed = [ False ] * 8
    fake_button_on = [ 0 ] * 8
    screen = machine.screen
    special_keys = {
            'o': machine.yes,
            'n': machine.no,
            'g': machine.go
            }
   

    # RPi_pins corresponds to player number
    rpi_pins = [ 3,5,10,8,19,21,24,26 ]
    eventq = []

    def channel_down(channel):
        eventq.append(channel)

    GPIO.setmode(GPIO.BOARD)    
    GPIO.setup (rpi_pins , GPIO.IN , pull_up_down=GPIO.PUD_UP )

    for chan in rpi_pins:
        GPIO.add_event_detect(chan,GPIO.FALLING,channel_down,20)

    try:
        one_second = time.time()
        while True:
            ch = screen.getch()
            for n in range(len(button_pressed)):
                button_pressed[n] = GPIO.input(rpi_pins[n]) == GPIO.LOW
            if len(eventq) > 0:
                player = rpi_pins.index(eventq.pop())
                machine.hitBuzzer(num = player,buttons=button_pressed)
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
        GPIO.cleanup()
        screen.cleanup()   
        

def main():
    logging.basicConfig(stream=file("funquiz.log","w"), level=logging.INFO)
    transitions.logger.setLevel(logging.DEBUG)
    game = Game()
    feed_events(game)
    

if __name__ == "__main__":
    main()
