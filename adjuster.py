#!/usr/bin/env python3.6
import re
import urllib.request
from base64 import b64encode
from time import sleep, strftime, localtime, monotonic
from os.path import exists as pth_ex
from os import makedirs
import threading
use_gpio = False
if use_gpio:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BOARD) # use pin numbering, not "GPIO" numbering https://raspberrypi.stackexchange.com/a/12967
    relaypins = [13, 15, 16, 18]
    for x in relaypins:
        GPIO.setup(x, GPIO.OUT)

# webpage parameters
# webpage = [regex, webpage, optionalauth]
# if you are having a hard time with regex, try https://regex101.com (it's a vis tool)
# webpage = [r'(?P<battpercent>.*)', 'http://192.168.1.2/DashBoard.htm']
# webpage = [r'(?P<battpercent>.*)', 'http://192.168.1.2/DashBoard.htm', 'admin:password']
webpage = [r'(?P<battpercent>.*)', 'http://localhost:8000/page.txt']
tcharge = 80 # target charge in percentage
tchgvtk = 2 # target charge give or take a few percent
speartime = 10.0 # spear valve seconds between states

sprtchlimitaft = 5000 # go to minimum and maximum of spear valve after x spear adjustments
spminadj = 0.1 # minimum spear adjustment value

# program parameters
valvemult = 1 # automatic valve correction multiplier (0=disabled)
loglevel = 0 # log level for console
csvwrite = False # write csv files
pollrate = 60 # polling rate (in seconds) (higher = less equipment wear, lower = quicker adjust)

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

def dontblock(fn): # function wrapper to turn said function into a thread
    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread
    return wrapper

class spearvalve(object):
    """docstring for spearvalve"""
    def touchlimits(self): # touch both limits to reset any drift
        gobackto = self.ps
        self.goto(0)
        self.goto(1)
        self.goto(gobackto)
    def goto(self, *args, **kwargs): # set the spear valve to a position
        # acts like non-blocking function unless it's already running
        if self.adjcount > sprtchlimitaft: # touch limits after adjustment amount
            self.adjcount = 0
            self.touchlimits()
            self.adjcount = 0
        try: self.th.join() # block on behalf of existing threadhandle
        except: pass
        def thread(position): # the blocking function
            global spminadj
            global sprtchlimitaft
            if not (0 <= position <= 1):
                log(f'invalid spearvalve position specified ({position})', 1)
                return
            relpos = position-self.ps
            if abs(relpos) >= spminadj: # if need to move
                log(f'move spear to {position} ({relpos})')
                relay_set(2, (relpos < 0)) # set polarity for direction
                relay_set(3, True)
                sleep(abs(relpos)*self.mtm) # move relative direction on timescale
                relay_set(3, False)
                if 'fh' not in vars(): # set file handle
                    self.fh = open(self.flnm, 'w')
                self.ps = position
                self.fh.seek(0)
                self.fh.write(str(self.ps))
                self.fh.truncate()
                self.adjcount = self.adjcount+1
        self.th = threading.Thread(target=thread, args=args, kwargs=kwargs) # set threadhandle
        self.th.start()
        return(self.th)
    def __init__(self, rlpolarity, rlenable, motortime):
        super(spearvalve, self).__init__()
        self.adjcount = 0 # spear adjustment counter (auto-touchlimits)
        self.mtm = motortime
        self.rlpl = rlpolarity
        self.rlen = rlenable
        self.flnm = f"spear_{self.rlen}.txt"
        self.ps = 0
        if pth_ex(self.flnm): # read spear valve position from file if possible
            self.ps = float(open(self.flnm, 'r').read())
            log(f'valve pos at {self.ps}')
        self.goto(self.ps)

nozzle = {'actuator': [0, 1], 'spear': spearvalve(2, 3, speartime)}

# spear = spearvalve(2, 3, speartime)
# spear.goto(0.3)
# spear.touchlimits()
# print(f'spear pos: {spear.ps}')

mtonic_tm = 0 # timekeeper variable
v_state = 0 # valve state variable
vstflnm = 'valvestate.txt'
if pth_ex(vstflnm): # valve position from file if possible
    v_state = float(open(vstflnm, 'r').read())
    log(f'valve state at {v_state}')
while True:
    try:
        while not int(monotonic()) >= mtonic_tm+pollrate: # more accurate wait method, based on sysclock
            sleep(pollrate/10)
        mtonic_tm = int(monotonic())
        csv = {strftime("h:m:s (%z)", localtime()): strftime("%H:%M:%S", localtime())}
        regmatch = re.match(webpage[:1][0], fetchpage(*webpage[1:])) # read+match data from webpage
        csv['batterylvl'] = float(regmatch['battpercent']) # raise error if not a number
        if csv['batterylvl'] > 100 or csv['batterylvl'] < 0: # raise error if not a percentage
            raise ValueError(f"battery charge {csv['batterylvl']} percentage not in range 0-100")
        cr = float(tcharge - csv['batterylvl'])
        csv['correction'] = int(cr) # use int to save on csv filesize
        
        if csvwrite: # append data to csv file
            csv_a(csv)
        # log(csv) # log variables to debug console

        # log(f'valve state at {v_state}')
        if valvemult != 0 and abs(cr) > tchgvtk: # take action on calculated correction
            nvst = min(len(nozzle['actuator'])+1, max(0, v_state+(cr/10000*pollrate*valvemult)))
            if nvst != v_state: # if valve state changed
                # log(f'new valve state {nvst}')
                for x in nozzle['actuator']:
                    relay_set(x, (int(nvst) > x))
                nozzle['spear'].goto(max(nvst%1, nvst-len(nozzle['actuator'])))

                if 'vst' not in vars(): # valve-state file handle
                    vst = open(vstflnm, 'w')
                v_state = nvst
                vst.seek(0)
                vst.write(str(v_state)) # write valve state
                vst.truncate()


    except Exception as e:
        log(e, 1)
        sleep(2)