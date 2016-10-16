# -*- coding: utf-8 -*-

"""Aquoscmd - control Sharp Aquos TV through serial port

テレビの「クイック起動」を有効にしないとリモコンでテレビを消した時にRS232でONコマンドを送信してもERRになる

Revision history
20160703 v01; first release
"""

import serial
from time import sleep

CMD_VOLM = b'\x56\x4F\x4C\x4D\x3F\x20\x20\x20\x0d'          #get current volume
CMD_VOLS = b'\x56\x4F\x4C\x4D\x33\x30\x20\x20\x0d'          #set volume to 30
CMD_POWR_STATUS = b'\x50\x4F\x57\x52\x3F\x3F\x3F\x3F\x0d'   #get power status 1 = ON, 0 = OFF
CMD_POWR_ON = b'\x50\x4F\x57\x52\x20\x20\x20\x31\x0d'       #turn TV on
CMD_POWR_OFF = b'\x50\x4F\x57\x52\x20\x20\x20\x30\x0d'      #turn TV off
CMD_INP1 = b'\x49\x41\x56\x44\x20\x20\x20\x31\x0d'          #set TV to input1
CMD_RSPW1 = b'\x52\x53\x50\x57\x20\x20\x20\x31\x0d'         #enable power on via serial ?
CMD_RSPW1ALT = b'\x52\x53\x50\x57\x31\x20\x20\x20\x0d'      #either this or the above command is correct. both give OK as a reponse

def send_RS232_command(command):
    """Send command to TV via RS232"""
    ser.write(command)
    sleep(0.25)
    msg = ser.readline()
    while ser.inWaiting() > 0:
            msg += ser.readline()
    # convert byte array to ascii string, strip newline chars
    return str(msg, 'ascii').rstrip('\r\n')

if __name__ == '__main__':
    # Attempt serial connection 
    try:
        ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
        print('Connected to serial successfully')
    except serial.SerialException:
        print('No device detected or could not connect - attempting reconnect in 5 seconds')
        time.sleep(5)
        ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
        
    power_status = send_RS232_command(CMD_POWR_STATUS)
    if (power_status == '1'):
        #if TV is already on, switch to input 1 (HDMI)
        response = send_RS232_command(CMD_INP1)
        if (response == 'OK'):
            print('successfully switched to input1')
    elif (power_status == '0'):
        #if TV is off, turn it on and then switch to input 1 (HDMI)
        response = send_RS232_command(CMD_POWR_ON)
        if (response == 'OK'):
            print('successfully switched on TV')
            response = send_RS232_command(CMD_INP1)
            if (response == 'OK'):
                print('successfully switched to input1')