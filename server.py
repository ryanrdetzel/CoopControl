from socket import *
from threading import Thread
import thread
import pytz
import time
import datetime
import RPi.GPIO as GPIO
from astral import Astral

# Hold either button for 2 seconds to switch modes
# In auto buttons Stop for 60 seconds. Again, continues
# In manual, left goes up assuming it's not up. right goes down assuming
#  any button while moving stops it
# Todo:
# Record how long it takes to open the door, close
# ERror states

class Door(object):
    MAX_MANUAL_MODE_TIME = 60 * 60
    AFTER_SUNSET_DELAY = 30
    IDLE = UNKNOWN = NOT_TRIGGERED = AUTO = 0
    UP = OPEN = TRIGGERED = MANUAL = 1
    DOWN = CLOSED = 2

    PIN_LED = 5

    def __init__(self):
        self.door_status = Door.UNKNOWN
        self.direction = Door.IDLE
        self.door_mode = Door.AUTO
        self.manual_mode_start = 0

        a = Astral()
        self.city = a["Boston"]
        self.setup_pins()

        t1 = Thread(target = self.checkInputs)
        t2 = Thread(target = self.checkTime)
        t1.setDaemon(True)
        t2.setDaemon(True)
        t1.start()
        t2.start()

        host = 'localhost'
        port = 55567
        addr = (host, port)

        serversocket = socket(AF_INET, SOCK_STREAM)
        serversocket.bind(addr)
        serversocket.listen(2)

        # Get door position
        self.changeDoorMode(Door.AUTO)
        self.stopDoor(0)

        ## Setup buttons
        GPIO.add_event_detect(13, GPIO.RISING, callback=self.buttonPress, bouncetime=200)
        GPIO.add_event_detect(19, GPIO.RISING, callback=self.buttonPress, bouncetime=200)

        while True:
            try:
                print "Server is listening for connections\n"
         
                clientsocket, clientaddr = serversocket.accept()
                thread.start_new_thread(handler, (clientsocket, clientaddr))
            except KeyboardInterrupt:
                break
            time.sleep(0.01)

        print "Close connection"
        GPIO.output(Door.PIN_LED, GPIO.LOW)
        serversocket.close()
        self.stopDoor(0)

    def setup_pins(self):
        GPIO.setmode(GPIO.BCM)

        GPIO.setup(18, GPIO.OUT)
        GPIO.setup(12, GPIO.OUT)
        GPIO.setup(16, GPIO.OUT)
        GPIO.setup(Door.PIN_LED, GPIO.OUT)  #LED
        GPIO.setup(21, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(20, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(13, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(19, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    def closeDoor(self):
        (top, bottom) = self.currentInputStatus()
        if (bottom == Door.TRIGGERED):
            print "Door is already closed"
            return
        print "Closing door"
        GPIO.output(18, GPIO.HIGH)
        GPIO.output(12, GPIO.LOW)
        GPIO.output(16, GPIO.HIGH)
        self.direction = Door.DOWN

    def openDoor(self):
        (top, bottom) = self.currentInputStatus()
        if (top == Door.TRIGGERED):
            print "Door is already open"
            return
        print "Opening door"
        GPIO.output(18, GPIO.HIGH)
        GPIO.output(12, GPIO.HIGH)
        GPIO.output(16, GPIO.LOW)
        self.direction= Door.UP

    def stopDoor(self, delay):
        print "Stop door"
        time.sleep(delay)
        GPIO.output(18, GPIO.LOW)
        GPIO.output(12, GPIO.LOW)
        GPIO.output(16, GPIO.LOW)
        self.direction = Door.IDLE

        (top, bottom) = self.currentInputStatus()
        if (top == Door.TRIGGERED):
            print "Door is open"
            self.door_status = Door.OPEN
        elif (bottom == Door.TRIGGERED):
            print "Door is closed"
            self.door_status = Door.CLOSED
        else:
            self.door_status = Door.UNKNOWN

    def checkTime(self):
        while True:
            if self.door_mode == Door.AUTO:
                current = datetime.datetime.now(pytz.timezone('US/Eastern'))
                sun = self.city.sun(date=datetime.datetime.now(), local=True)

                after_sunset = sun["sunset"] + datetime.timedelta(minutes = Door.AFTER_SUNSET_DELAY)

                if (current < sun["sunrise"] or current > after_sunset) and self.door_status != Door.CLOSED and self.direction != Door.DOWN:
                    print "Door should be closed"
                    self.closeDoor()
                elif current > sun["sunrise"] and current < after_sunset and self.door_status != Door.OPEN and self.direction != Door.UP:
                    print "Door should be open"
                    self.openDoor()
            time.sleep(1)

    def currentInputStatus(self):
        bottom = GPIO.input(21)
        top = GPIO.input(20)
        return (top, bottom)

    def checkInputs(self):
        while True:
            (top, bottom) = self.currentInputStatus()
            if (self.direction == Door.UP and top == Door.TRIGGERED):
                self.stopDoor(0)
            if (self.direction == Door.DOWN and bottom == Door.TRIGGERED):
                self.stopDoor(1)
            time.sleep(0.01)

    def blink(self):
        while(self.door_mode == Door.MANUAL):
            GPIO.output(Door.PIN_LED, GPIO.LOW)
            time.sleep(1)
            GPIO.output(Door.PIN_LED, GPIO.HIGH)
            time.sleep(1)
            print (time.time()) - self.manual_mode_start
            if int(time.time()) - self.manual_mode_start > Door.MAX_MANUAL_MODE_TIME:
                print "In manual mode too long"
                self.changeDoorMode(Door.AUTO)

    def changeDoorMode(self, new_mode):
        if new_mode == Door.AUTO: 
            print "Enter auto mode"
            self.door_mode = Door.AUTO
            GPIO.output(Door.PIN_LED, GPIO.HIGH)
        else:
            print "Enter manual mode"
            self.door_mode = Door.MANUAL
            self.stopDoor(0)
            
            self.manual_mode_start = int(time.time())

            t2 = Thread(target = self.blink)
            t2.setDaemon(True)
            t2.start()
            
    def buttonPress(self, button):
        print "Starting button..."
        start = end = int(round(time.time() * 1000))
        waiting = True
        while GPIO.input(button) and waiting:
            end = int(round(time.time() * 1000))
            diff = end - start
            if (diff >= 2000):
                waiting = False
                if (self.door_mode == Door.AUTO):
                    self.changeDoorMode(Door.MANUAL)
                else:
                    self.changeDoorMode(Door.AUTO)
                return
            time.sleep(0.1)
        print "Ending"
     
        # Quick touch, what mode?
        if (self.door_mode == Door.MANUAL):
            if (self.direction != Door.IDLE):
                self.stopDoor(0)
            elif (button == 13):
                self.openDoor()
            else:
                self.closeDoor()

    def handler(self, clientsocket, clientaddr):
        print "Accepted connection from: ", clientaddr
     
        while True:
            data = clientsocket.recv(1024)
            if not data:
                break
            else:
                data = data.strip()
                if (data == 'stop'):
                    self.stopDoor(0)
                elif (data == 'open'):
                    self.openDoor()
                elif (data == 'close'):
                    self.closeDoor()
                #msg = "You sent me: %s" % data
                #clientsocket.send(msg)
            time.sleep(0.01)
        clientsocket.close()

if __name__ == "__main__":
    door = Door()
