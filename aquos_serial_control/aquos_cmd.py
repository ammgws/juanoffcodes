#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Aquos_cmd - control Sharp Aquos TV through serial port.

To use these commands with Yatse (Kodi remote control app for Android), create a Custom Command in Yatse:
RunScript(special://home/addons/aquous_serial_control/aquos_cmd.py, -h)
* Copy aquos_serial_control into the ~/.kodi/addons/ directory
* Install pyserial to Kodi's python interpretor (may need to install pip first)
* If get permission errors wrt opening serial port, add the user to the dialout group:
sudo usermod -a -G dialout kodi

テレビの「クイック起動」を有効にしないとリモコンでテレビを消した時にRS232でONコマンドを送信してもERRになる

Revision history
20160703 v01; first release
20161016 v02; allow use as command line app (still a WIP)
"""
# standard library
from __future__ import absolute_import, division, print_function, unicode_literals  # Kodi only supports python2 atm
from argparse import ArgumentParser
from time import sleep

# third party imports
import serial


SPACE = b' '
CMD_END = b'\x0d'
CMD_POWR_STATUS = b'\x50\x4F\x57\x52\x3F\x3F\x3F\x3F\x0d'  # get power status. 1 = ON, 0 = OFF
CMD_POWR_ON = b'\x50\x4F\x57\x52\x20\x20\x20\x31\x0d'  # turn TV on
CMD_POWR_OFF = b'\x50\x4F\x57\x52\x20\x20\x20\x30\x0d'  # turn TV off
CMD_INP1 = b'\x49\x41\x56\x44\x20\x20\x20\x31\x0d'  # set TV to input1
CMD_RSPW1 = b'\x52\x53\x50\x57\x20\x20\x20\x31\x0d'  # enable power on via serial ?
CMD_RSPW1ALT = b'\x52\x53\x50\x57\x31\x20\x20\x20\x0d'  # either this or the above is correct. both give OK as a reponse
CMD_VOLM = b'VOLM'  # header for volume command


class AquosControl:
    def __init__(self):
        # Attempt serial connection
        try:
            self.ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)
            print('Connected to TV successfully')
        except serial.SerialException:
            print('TV not detected or could not connect - attempting reconnect in 1 second')
            sleep(1)
            self.ser = serial.Serial('/dev/ttyUSB0', 9600, timeout=1)

    def send_rs232_command(self, command):
        """Send command to TV via RS232"""
        self.ser.write(command)
        sleep(0.25)
        msg = self.ser.readline()
        while self.ser.inWaiting() > 0:
            msg += self.ser.readline()
        return msg.decode().strip()  # convert bytes to text string. works on both python 2 and 3

    def tv_power(self, command):
        if command == 0:
            response = self.send_rs232_command(CMD_POWR_OFF)
            print(response)
        elif command == 1:
            response = self.send_rs232_command(CMD_POWR_ON)
            print(response)
        elif command == 2:
            response = self.toggle_power()
            print(response)

    def toggle_power(self):
        power_status = self.send_rs232_command(CMD_POWR_STATUS)
        print('Current TV power status: {0}'.format(power_status))
        if power_status == '0':
            response = self.send_rs232_command(CMD_POWR_ON)
        elif power_status == '1':
            response = self.send_rs232_command(CMD_POWR_OFF)
        return response

    def prepare_for_htpc(self):
        """ Turn TV on, switch to HTPC input, set volume to preset level for watching movies/tv shows.
            Sets volume at a lower preset level in between switching to prevent
            loud sounds when first turning on TV and its on some random channel."""
        power_status = self.send_rs232_command(CMD_POWR_STATUS)
        print('TV power status: {0}'.format(power_status))
        if power_status == '1':
            # if TV is already on, switch to input 1 (HDMI)
            self.set_volume_to(15)
            response = self.send_rs232_command(CMD_INP1)
            if response == 'OK':
                print('Successfully switched to input1')
        elif power_status == '0':
            # if TV is off, turn it on and then switch to input 1 (HDMI)
            response = self.send_rs232_command(CMD_POWR_ON)
            print(response)
            if response == 'OK':
                print('Successfully switched on TV')
                self.set_volume_to(15)
                response = self.send_rs232_command(CMD_INP1)
                print(response)
                if response == 'OK':
                    print('Successfully switched to input1')
        self.set_volume_to(30)

    def set_volume_to(self, vol):
        command = self.build_command(CMD_VOLM, str(vol).encode())
        response = self.send_rs232_command(command)
        return response

    @staticmethod
    def build_command(header, parameter):
        # Command format:
        # COMMAND     | PARAMETER
        # [] [] [] []   [] [] [] []
        return header + parameter + (4 - len(parameter)) * SPACE + CMD_END


def main(arguments):
    # Get command line arguments
    parser = ArgumentParser(description='Send command to Sharp AQUOS TV.', add_help=False)  # disable default '-h' flag
    parser.add_argument('-v', '--volume',
                        type=int, default=-1,
                        dest='volume',
                        help='Set volume level.')
    parser.add_argument('-i', '--input',
                        type=int,
                        help='Change input channel.')
    parser.add_argument('-h', '--htpc',
                        dest='htpc', action='store_const',
                        const=1, default=0,
                        help='Prepare TV for HTPC by turning it on and changing the input channel.')
    parser.add_argument('-p', '--power',
                        dest='power',
                        type=int, default=-1,
                        help='Set TV power state.')
    args = parser.parse_args(arguments)

    controller = AquosControl()
    if args.volume != -1:
        print('Setting volume to {0}'.format(args.volume))
        controller.set_volume_to(args.volume)
    elif args.power != -1:
        print('Changing TV power state')
        controller.tv_power(args.power)
    elif args.htpc:
        print('Preparing TV for HTPC')
        controller.prepare_for_htpc()


if __name__ == '__main__':
    from sys import argv  # pylint: disable=C0412

    main(argv[1:])
