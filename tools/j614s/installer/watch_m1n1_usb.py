#!/usr/bin/env python3
"""Read-only USB m1n1 enumeration watch from a SECOND macOS/Linux computer.

Run BEFORE selecting Gravity Linux on the target. This does not open a serial
port, change boot state, or require third-party Python packages.
"""
import argparse, datetime, glob, os, platform, subprocess, time
from pathlib import Path

def devices():
    if platform.system() == 'Darwin':
        paths=glob.glob('/dev/cu.usbmodem*')+glob.glob('/dev/tty.usbmodem*')
    elif platform.system() == 'Linux':
        paths=glob.glob('/dev/ttyACM*')
    else:
        raise SystemExit('Supported hosts: macOS, Linux')
    return sorted(set(paths))

def stamp():
    return datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds',type=int,default=180)
    p.add_argument('--log',type=Path,default=Path('m1n1-usb-watch.log'))
    a=p.parse_args()
    if a.seconds<1: p.error('seconds must be positive')
    def emit(msg):
        line=f'[{stamp()}] {msg}'
        print(line,flush=True)
        with a.log.open('a') as f:f.write(line+'\n')
    emit('Started passive USB serial enumeration; START THE WATCH BEFORE BOOTING THE TARGET')
    emit('Host: '+platform.platform())
    emit('Note: devices can be other hardware; m1n1 not confirmed by node name alone.')
    previous=None
    end=time.monotonic()+a.seconds
    while time.monotonic()<end:
        current=tuple(devices())
        if current!=previous:
            emit('Serial nodes: '+(', '.join(current) if current else '(none)'))
            added=set(current)-set(previous or ())
            for d in sorted(added):emit('ADDED '+d)
            removed=set(previous or ())-set(current)
            for d in sorted(removed):emit('REMOVED '+d)
            previous=current
        time.sleep(0.25)
    emit('Finished. Absence of USB nodes does not prove m1n1 did not execute.')
    emit('If nodes appeared, confirm USB manufacturer/product and test proxyclient in a separate controlled step.')
if __name__=='__main__':main()
