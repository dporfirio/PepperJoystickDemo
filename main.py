import sys
import time
import pygame
import select
import threading
import json
from socket import socket, AF_INET, SOCK_STREAM


class Client:

    def __init__(self):
        self.s = None
        self.event_ds_lock = threading.Lock()
        self.ev = {
            "velocity": 0.0,
            "twist": 0.0,
            "a": 0,
            "b": 0,
            "x": 0,
            "y": 0,
            "lb": 0,
            "rb": 0,
            "info": 0,
            "start": 0,
            "center": 0,
            "left joy button": 0,
            "right joy button": 0,
            "up": 0,
            "down": 0,
            "left": 0,
            "right": 0
        }
        self.connect_to_robot(sys.argv[1])
        thread = threading.Thread(target=self.send_ev_ds)
        thread.daemon = True        # Daemonize thread
        thread.start()

    def connect_to_robot(self, ip):
        while True:
            try:
                self.s = socket(AF_INET, SOCK_STREAM)
                self.s.connect((ip, 8888))
                break
            except:
                print("Unable to connect to robot at {}:8888. Is server running?".format(ip))
            time.sleep(1)

    def send_ev_ds(self):
        while True:
            time.sleep(0.05)  # 20 hz
            self.event_ds_lock.acquire()
            s = json.dumps(self.ev) + "\n"
            try:
                read_s, write_s, exceptional = select.select([], [self.s], [])
                write_s[0].send(str.encode(s))
            except:
                print("not connected yet")
            self.event_ds_lock.release()

    def reset_event_ds_buttons(self):
        self.event_ds_lock.acquire()
        self.ev = {
            "velocity": self.ev["velocity"],
            "twist": self.ev["twist"],
            "a": 0,
            "b": 0,
            "x": 0,
            "y": 0,
            "lb": 0,
            "rb": 0,
            "info": 0,
            "start": 0,
            "center": 0,
            "left joy button": 0,
            "right joy button": 0,
            "up": 0,
            "down": 0,
            "left": 0,
            "right": 0
        }
        self.event_ds_lock.release()

    def update_event_ds(self, key, val):
        self.event_ds_lock.acquire()
        self.ev[key] = val
        self.event_ds_lock.release()

    def gamepad_loop(self):
        pygame.init()
        joysticks = []
        clock = pygame.time.Clock()
        keepPlaying = True

        # there really should only be one joystick
        for i in range(0, pygame.joystick.get_count()):
            joysticks.append(pygame.joystick.Joystick(i))
            joysticks[-1].init()
            print ("Detected joystick "), joysticks[-1].get_name()
        while keepPlaying:
            clock.tick(20)
            self.reset_event_ds_buttons()
            for event in pygame.event.get():
                if event.type == pygame.JOYAXISMOTION:
                    if event.axis == 1 and event.value > 0:
                        self.update_event_ds("velocity", -1 * event.value if event.value > 0.6 else 0.0)
                    elif event.axis == 1:
                        self.update_event_ds("velocity", -1 * event.value if event.value < -0.6 else 0.0)
                    if event.axis == 3 and event.value > 0:
                        self.update_event_ds("twist", event.value if event.value > 0.6 else 0.0)
                    elif event.axis == 3:
                        self.update_event_ds("twist", event.value if event.value < -0.6 else 0.0)
                elif event.type == pygame.JOYBUTTONUP:
                    if event.button == 0:
                        print("a")
                        self.update_event_ds("a", 1)
                    if event.button == 1:
                        print("b")
                        self.update_event_ds("b", 1)
                    if event.button == 2:
                        print("x")
                        self.update_event_ds("x", 1)
                    if event.button == 3:
                        print("y")
                        self.update_event_ds("y", 1)
                    if event.button == 4:
                        print("lb")
                        self.update_event_ds("lb", 1)
                    if event.button == 5:
                        print("rb")
                        self.update_event_ds("rb", 1)
                    if event.button == 6:
                        print("info")
                        self.update_event_ds("info", 1)
                    if event.button == 7:
                        print("start")
                        self.update_event_ds("start", 1)
                    if event.button == 8:
                        print("center")
                        self.update_event_ds("center", 1)
                    if event.button == 9:
                        print("left joy button")
                        self.update_event_ds("left joy button", 1)
                    if event.button == 10:
                        print("right joy button")
                        self.update_event_ds("right joy button", 1)
                elif event.type == pygame.JOYHATMOTION:
                    val = None
                    if event.value[0] == 1:
                        val = "right"
                    elif event.value[0] == -1:
                        val = "left"
                    elif event.value[1] == 1:
                        val = "up"
                    elif event.value[1] == -1:
                        val = "down"
                    if val is not None:
                        print(val)
                        self.update_event_ds(val, 1)

                        
if __name__ == "__main__":
    client = Client()
    client.gamepad_loop()
