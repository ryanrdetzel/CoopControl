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

MAX_MANUAL_MODE_TIME = 60 * 60

AUTO = 0
MANUAL = 1

NOT_TRIGGERED = 0
TRIGGERED = 1

IDLE = UNKNOWN = 0
UP = OPEN = 1
DOWN = CLOSED = 2

door_status = UNKNOWN
direction = IDLE
door_mode = AUTO
manual_mode_start = 0

a = Astral()
city = a["Boston"]

GPIO.setmode(GPIO.BCM)

GPIO.setup(18, GPIO.OUT)
GPIO.setup(12, GPIO.OUT)
GPIO.setup(16, GPIO.OUT)
GPIO.setup(26, GPIO.OUT)  #LED
GPIO.setup(21, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(20, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(13, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(19, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

def closeDoor():
    global direction 
    (top, bottom) = currentInputStatus()
    if (bottom == TRIGGERED):
        print "Door is already closed"
        return
    print "Closing door"
    GPIO.output(18, GPIO.HIGH)
    GPIO.output(12, GPIO.LOW)
    GPIO.output(16, GPIO.HIGH)
    direction = DOWN

def openDoor():
    global direction 
    (top, bottom) = currentInputStatus()
    if (top == TRIGGERED):
        print "Door is already open"
        return
    print "Opening door"
    GPIO.output(18, GPIO.HIGH)
    GPIO.output(12, GPIO.HIGH)
    GPIO.output(16, GPIO.LOW)
    direction= UP

def stopDoor(delay):
    global direction, door_status

    print "Stop door"
    time.sleep(delay)
    GPIO.output(18, GPIO.LOW)
    GPIO.output(12, GPIO.LOW)
    GPIO.output(16, GPIO.LOW)
    direction = IDLE

    (top, bottom) = currentInputStatus()
    if (top == TRIGGERED):
        print "Door is open"
        door_status = OPEN
    elif (bottom == TRIGGERED):
        print "Door is closed"
        door_status = CLOSED
    else:
        door_status = UNKNOWN

def checkTime():
    global door_mode, door_status, direction
    while True:
        if door_mode == AUTO:
            current = datetime.datetime.now(pytz.timezone('US/Eastern'))
            sun = city.sun(date=datetime.datetime.now(), local=True)

            #print sun["sunset"]
            #print current
            #print sun["sunset"] - current

            if (current < sun["sunrise"] or current > sun["sunset"]) and door_status != CLOSED and direction != DOWN:
                print "Door should be closed"
                closeDoor()
            elif current > sun["sunrise"] and current < sun["sunset"] and door_status != OPEN and direction != UP:
                print "Door should be open"
                openDoor()
        time.sleep(1)

def currentInputStatus():
    bottom = GPIO.input(21)
    top = GPIO.input(20)
    return (top, bottom)

def checkInputs():
    while True:
        (top, bottom) = currentInputStatus()
        if (direction == UP and top == TRIGGERED):
            stopDoor(0)
        if (direction == DOWN and bottom == TRIGGERED):
            stopDoor(1)
        time.sleep(0.01)

def blink():
    global door_mode, manual_mode_start
    while(door_mode == MANUAL):
        GPIO.output(26, GPIO.LOW)
        time.sleep(1)
        GPIO.output(26, GPIO.HIGH)
        time.sleep(1)
        print (time.time()) - manual_mode_start
        if int(time.time()) - manual_mode_start > MAX_MANUAL_MODE_TIME:
            print "In manual mode too long"
            changeDoorMode(AUTO)

def changeDoorMode(new_mode):
    global door_mode, manual_mode_start
    if new_mode == AUTO: 
        print "Enter auto mode"
        door_mode = AUTO
        GPIO.output(26, GPIO.HIGH)
    else:
        print "Enter manual mode"
        door_mode = MANUAL
        stopDoor(0)
        
        manual_mode_start = int(time.time())

        t2 = Thread(target = blink)
        t2.setDaemon(True)
        t2.start()
        
def buttonPress(button):
    global door_mode, direction, door_status, manual_mode_start

    print "Starting button..."
    start = end = int(round(time.time() * 1000))
    waiting = True
    while GPIO.input(button) and waiting:
        end = int(round(time.time() * 1000))
        diff = end - start
        if (diff >= 2000):
            waiting = False
            if (door_mode == AUTO):
                changeDoorMode(MANUAL)
            else:
                changeDoorMode(AUTO)
            return
        time.sleep(0.1)
    print "Ending"
 
    # Quick touch, what mode?
    if (door_mode == MANUAL):
        if (direction != IDLE):
            stopDoor(0)
        elif (button == 13):
            openDoor()
        else:
            closeDoor()

def handler(clientsocket, clientaddr):
    print "Accepted connection from: ", clientaddr
 
    while True:
        data = clientsocket.recv(1024)
        if not data:
            break
        else:
            data = data.strip()
            if (data == 'stop'):
                stopDoor(0)
            elif (data == 'open'):
                openDoor()
            elif (data == 'close'):
                closeDoor()
            #msg = "You sent me: %s" % data
            #clientsocket.send(msg)
        time.sleep(0.01)
    clientsocket.close()

if __name__ == "__main__":
    t1 = Thread(target = checkInputs)
    t2 = Thread(target = checkTime)
    t1.setDaemon(True)
    t2.setDaemon(True)
    t1.start()
    t2.start()

    host = 'localhost'
    port = 55567
    buf = 1024
 
    addr = (host, port)

    serversocket = socket(AF_INET, SOCK_STREAM)
    #serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    serversocket.bind(addr)
    serversocket.listen(2)

    # Get door position
    direction = IDLE
    changeDoorMode(AUTO)
    stopDoor(0)

    ## Setup buttons
    GPIO.add_event_detect(13, GPIO.RISING, callback=buttonPress, bouncetime=200)
    GPIO.add_event_detect(19, GPIO.RISING, callback=buttonPress, bouncetime=200)

    while True:
        try:
            print "Server is listening for connections\n"
     
            clientsocket, clientaddr = serversocket.accept()
            thread.start_new_thread(handler, (clientsocket, clientaddr))
        except KeyboardInterrupt:
            break
        time.sleep(0.01)

    print "Close connection"
    GPIO.output(26, GPIO.LOW)
    serversocket.close()
    stopDoor(0)
