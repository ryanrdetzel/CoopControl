from socket import *
from threading import Thread
import thread
import time
import RPi.GPIO as GPIO

IDLE = 0
UP = 1
DOWN = 2

direction = IDLE

GPIO.setmode(GPIO.BCM)

GPIO.setup(18, GPIO.OUT)
GPIO.setup(12, GPIO.OUT)
GPIO.setup(16, GPIO.OUT)
GPIO.setup(21, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(20, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

def down():
    print "Close door"
    GPIO.output(18, GPIO.HIGH)
    GPIO.output(12, GPIO.LOW)
    GPIO.output(16, GPIO.HIGH)
    global direction 
    direction = DOWN

def up():
    print "Open door"
    GPIO.output(18, GPIO.HIGH)
    GPIO.output(12, GPIO.HIGH)
    GPIO.output(16, GPIO.LOW)
    global direction 
    direction= UP

def stop(delay):
    print "Stop door"
    time.sleep(delay)
    GPIO.output(18, GPIO.LOW)
    GPIO.output(12, GPIO.LOW)
    GPIO.output(16, GPIO.LOW)
    global direction 
    direction = IDLE

def checkInputs():
    while True:
        bottom = GPIO.input(21)
        top = GPIO.input(20)

        if (direction == UP and top == 1):
            stop(0)
        if (direction == DOWN and bottom == 1):
            stop(1)
 
def handler(clientsocket, clientaddr):
    print "Accepted connection from: ", clientaddr
 
    while 1:
        data = clientsocket.recv(1024)
        if not data:
            break
        else:
            data = data.strip()
            if (data == 'stop'):
                stop(0)
            elif (data == 'up'):
                up()
            elif (data == 'down'):
                down()
            #msg = "You sent me: %s" % data
            #clientsocket.send(msg)
    clientsocket.close()

if __name__ == "__main__":
    t1 = Thread(target = checkInputs)
    t1.setDaemon(True)
    t1.start()

    host = 'localhost'
    port = 55567
    buf = 1024
 
    addr = (host, port)
    serversocket = socket(AF_INET, SOCK_STREAM)
    serversocket.bind(addr)
    serversocket.listen(2)

    stop(0) 
    while 1:
        try:
            print "Server is listening for connections\n"
     
            clientsocket, clientaddr = serversocket.accept()
            thread.start_new_thread(handler, (clientsocket, clientaddr))
        except KeyboardInterrupt:
            break
    serversocket.close()
