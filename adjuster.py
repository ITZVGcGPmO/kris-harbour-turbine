#!/usr/bin/env python3.6
import re
import urllib.request
from base64 import b64encode
from time import sleep, strftime, localtime, monotonic
from os.path import exists as pth_ex
from os import makedirs
use_gpio = False
if use_gpio:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BOARD) # use pin numbering, not "GPIO" numbering https://raspberrypi.stackexchange.com/a/12967
    relaypins = [15, 16]
    for x in relaypins:
        GPIO.setup(x, GPIO.OUT)

# webpage parameters
# webpage = [regex, webpage, optionalauth]
# if you are having a hard time with regex, try https://regex101.com (it's a vis tool)
# webpage = [r'(?P<battpercent>.*)', 'http://192.168.1.2/DashBoard.htm']
# webpage = [r'(?P<battpercent>.*)', 'http://192.168.1.2/DashBoard.htm', 'admin:password']
webpage = [r'(?P<battpercent>.*)', 'http://localhost:8000/page.txt']
# target charge in percentage
tcharge = 80
# target charge give or take a few percent
tchgvtk = 2
# when x percent from target, fully saturate motors
tchsat = 10

# minimum on-time of relays/motors in seconds (don't turn them on/off quickly)
minontime = 1

# program parameters
loglevel = 0
csvwrite = False # write csv files
pollrate = 60 # poll every x seconds (less=more relay clicking, more=inaccurate adjustments)

loglevels = ['DBG', 'ERR']
def log(content, level=0): # log some output to the console
    global loglevel
    global loglevels
    if level >= loglevel:
        print(strftime("[%H:%M:%S]", localtime())+f' [{loglevels[level]}]: {content}')

def fetchpage(url, auth=False): # fetch page from url, with optional username:password
    log('fetching '+url)
    request = urllib.request.Request(url)
    if auth:
        request.add_header("Authorization", f"Basic {b64encode(str.encode(auth)).decode()}")   
    return(urllib.request.urlopen(request).read().decode())

def csv_a(csv): # append csv data to file, create files if need be
    global f
    flnm = strftime("datalog/%Y/%b/%d.csv", localtime())
    if 'f' not in vars() or f.name != flnm: # new file
        if 'f' in vars(): # close existing
            f.close()
        if not pth_ex(flnm): # create file if not exists
            makedirs(strftime("datalog/%Y/%b", localtime()), exist_ok=True)
            open(flnm, 'w').write(','.join(map(str, csv.keys()))+'\n') # csv header
        f = open(flnm, 'a') # set file handle
    f.write(','.join(map(str, csv.values()))+'\n') # write csv data

def relay_set(rl, value): # set a relay to true/false
    log(f'set relay {rl} to {value}')
    if use_gpio:
        GPIO.output(relaypins[rl], value) 

mtonic_tm = 0 # timekeeper variable
while True:
    try:
        while not int(monotonic()) >= mtonic_tm+pollrate: # more accurate wait method, based on sysclock
            relay_set(0, False) # while in idle, main relay should be off
            sleep(pollrate/10)
        mtonic_tm = int(monotonic())
        csv = {strftime("h:m:s (%z)", localtime()): strftime("%H:%M:%S", localtime())}
        regmatch = re.match(webpage[:1][0], fetchpage(*webpage[1:])) # read+match data from webpage
        csv['batterylvl'] = float(regmatch['battpercent']) # raise error if not a number
        if csv['batterylvl'] > 100 or csv['batterylvl'] < 0: # raise error if not a percentage
            raise ValueError(f"battery charge {csv['batterylvl']} percentage not in range 0-100")
        cr = float(tcharge - csv['batterylvl'])
        csv['correction'] = int(cr)
        
        if csvwrite: # append data to csv file
            csv_a(csv)
        log(csv) # log variables to debug console
        if abs(cr) > tchgvtk: # take action on calculated correction
            timeon = (abs(cr)-tchgvtk)/tchsat*pollrate
            if timeon >= minontime:
                relay_set(1, (cr < 0)) # set relay #2&3 on if negative
                relay_set(0, True) # keep main relay on for specific amount of time
                sleep(timeon)
    except Exception as e:
        log(e, 1)
        sleep(2)