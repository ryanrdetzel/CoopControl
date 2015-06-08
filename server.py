import logging
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


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

fh = logging.FileHandler('log.log')
fh.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

fh.setFormatter(formatter)
ch.setFormatter(formatter)
logger.addHandler(fh)
logger.addHandler(ch)


class Door(object):
    MAX_MANUAL_MODE_TIME = 60 * 60
    TIMEZONE_CITY = 'Boston'
    AFTER_SUNSET_DELAY = 30
    IDLE = UNKNOWN = NOT_TRIGGERED = AUTO = 0
    UP = OPEN = TRIGGERED = MANUAL = 1
    DOWN = CLOSED = 2

    PIN_LED = 5
    PIN_BUTTON_UP = 13
    PIN_BUTTON_DOWN = 19
    PIN_SENSOR_TOP = 20
    PIN_SENSOR_BOTTOM = 21
    PIN_MOTOR_ENABLE = 18
    PIN_MOTOR_A = 12
    PIN_MOTOR_B = 16

    def __init__(self):
        self.door_status = Door.UNKNOWN
        self.direction = Door.IDLE
        self.door_mode = Door.AUTO
        self.manual_mode_start = 0

        a = Astral()
        self.city = a[Door.TIMEZONE_CITY]
        self.setupPins()

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

        self.changeDoorMode(Door.AUTO)
        self.stopDoor(0)

        GPIO.add_event_detect(Door.PIN_BUTTON_UP, GPIO.RISING, callback=self.buttonPress, bouncetime=200)
        GPIO.add_event_detect(Door.PIN_BUTTON_DOWN, GPIO.RISING, callback=self.buttonPress, bouncetime=200)

        while True:
            try:
                logger.info("Server is listening for connections\n")
         
                clientsocket, clientaddr = serversocket.accept()
                thread.start_new_thread(handler, (clientsocket, clientaddr))
            except KeyboardInterrupt:
                break
            time.sleep(0.01)

        logger.info("Close connection")
        GPIO.output(Door.PIN_LED, GPIO.LOW)
        serversocket.close()
        self.stopDoor(0)

    def setupPins(self):
        GPIO.setmode(GPIO.BCM)

        GPIO.setup(Door.PIN_MOTOR_ENABLE, GPIO.OUT)
        GPIO.setup(Door.PIN_MOTOR_A, GPIO.OUT)
        GPIO.setup(Door.PIN_MOTOR_B, GPIO.OUT)
        GPIO.setup(Door.PIN_LED, GPIO.OUT) 
        GPIO.setup(Door.PIN_SENSOR_BOTTOM, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(Door.PIN_SENSOR_TOP, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(Door.PIN_BUTTON_UP, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
        GPIO.setup(Door.PIN_BUTTON_DOWN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    def closeDoor(self):
        (top, bottom) = self.currentInputStatus()
        if (bottom == Door.TRIGGERED):
            logger.info("Door is already closed")
            return
        logger.info("Closing door")
        GPIO.output(Door.PIN_MOTOR_ENABLE, GPIO.HIGH)
        GPIO.output(Door.PIN_MOTOR_A, GPIO.LOW)
        GPIO.output(Door.PIN_MOTOR_B, GPIO.HIGH)
        self.direction = Door.DOWN

    def openDoor(self):
        (top, bottom) = self.currentInputStatus()
        if (top == Door.TRIGGERED):
            logger.info("Door is already open")
            return
        logger.info("Opening door")
        GPIO.output(Door.PIN_MOTOR_ENABLE, GPIO.HIGH)
        GPIO.output(Door.PIN_MOTOR_A, GPIO.HIGH)
        GPIO.output(Door.PIN_MOTOR_B, GPIO.LOW)
        self.direction= Door.UP

    def stopDoor(self, delay):
        if self.direction != Door.IDLE:
            logger.info("Stop door")
            time.sleep(delay)
            GPIO.output(Door.PIN_MOTOR_ENABLE, GPIO.LOW)
            GPIO.output(Door.PIN_MOTOR_A, GPIO.LOW)
            GPIO.output(Door.PIN_MOTOR_B, GPIO.LOW)
            self.direction = Door.IDLE

        (top, bottom) = self.currentInputStatus()
        if (top == Door.TRIGGERED):
            logger.info("Door is open")
            self.door_status = Door.OPEN
        elif (bottom == Door.TRIGGERED):
            logger.info("Door is closed")
            self.door_status = Door.CLOSED
        else:
            logger.info("Door is in an unknown state")
            self.door_status = Door.UNKNOWN

    def checkTime(self):
        while True:
            if self.door_mode == Door.AUTO:
                current = datetime.datetime.now(pytz.timezone(self.city.timezone))
                sun = self.city.sun(date=datetime.datetime.now(), local=True)

                after_sunset = sun["sunset"] + datetime.timedelta(minutes = Door.AFTER_SUNSET_DELAY)

                if (current < sun["sunrise"] or current > after_sunset) and self.door_status != Door.CLOSED and self.direction != Door.DOWN:
                    logger.info("Door should be closed based on time")
                    self.closeDoor()
                elif current > sun["sunrise"] and current < after_sunset and self.door_status != Door.OPEN and self.direction != Door.UP:
                    logger.info("Door should be open based on time")
                    self.openDoor()
            time.sleep(1)

    def currentInputStatus(self):
        bottom = GPIO.input(Door.PIN_SENSOR_BOTTOM)
        top = GPIO.input(Door.PIN_SENSOR_TOP)
        return (top, bottom)

    def checkInputs(self):
        while True:
            (top, bottom) = self.currentInputStatus()
            if (self.direction == Door.UP and top == Door.TRIGGERED):
                logger.info("Top sensor triggered")
                self.stopDoor(0)
            if (self.direction == Door.DOWN and bottom == Door.TRIGGERED):
                logger.info("Bottom sensor triggered")
                self.stopDoor(1)
            time.sleep(0.01)

    def blink(self):
        while(self.door_mode == Door.MANUAL):
            GPIO.output(Door.PIN_LED, GPIO.LOW)
            time.sleep(1)
            GPIO.output(Door.PIN_LED, GPIO.HIGH)
            time.sleep(1)
            if int(time.time()) - self.manual_mode_start > Door.MAX_MANUAL_MODE_TIME:
                logger.info("In manual mode too long, switching")
                self.changeDoorMode(Door.AUTO)

    def changeDoorMode(self, new_mode):
        if new_mode == Door.AUTO: 
            logger.info("Entered auto mode")
            self.door_mode = Door.AUTO
            GPIO.output(Door.PIN_LED, GPIO.HIGH)
        else:
            logger.info("Entered manual mode")
            self.door_mode = Door.MANUAL
            self.stopDoor(0)
            
            self.manual_mode_start = int(time.time())

            t2 = Thread(target = self.blink)
            t2.setDaemon(True)
            t2.start()
            
    def buttonPress(self, button):
        waiting = True
        start = end = int(round(time.time() * 1000))

        while GPIO.input(button) and waiting:
            end = int(round(time.time() * 1000))
            if end - start >= 2000:
                if self.door_mode == Door.AUTO:
                    self.changeDoorMode(Door.MANUAL)
                else:
                    self.changeDoorMode(Door.AUTO)
                time.sleep(2)
                waiting = False
                return
            time.sleep(0.1)
     
        # Quick touch, what mode?
        if self.door_mode == Door.MANUAL:
            if self.direction != Door.IDLE:
                self.stopDoor(0)
            elif (button == Door.PIN_BUTTON_UP):
                self.openDoor()
            else:
                self.closeDoor()

    def handler(self, clientsocket, clientaddr):
        logger.info("Accepted connection from: ", clientaddr)
     
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
