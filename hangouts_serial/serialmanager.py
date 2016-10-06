#!/usr/bin/env python3

# Python Standard Library imports
import logging
from threading import Thread
from time import sleep
# Third party imports
import serial

class SerialManager(Thread):
    '''Class for handling intermediary communication between hardware connected
    to the serial port and Python. By using queues to pass commands to/responses
    from the serial port, it can be shared between multiple Python threads, or
    processes if changed to use multiprocessing module instead.'''

    def __init__(self, port, command_queue, response_queue, blocking=False, eolchar=b'xFF'):
        Thread.__init__(self)
        if not blocking:
            self.daemon = True  # Thread class default is False

        self.eolchar = eolchar

        # Setup communication queues
        self.command_queue = command_queue
        self.response_queue = response_queue

        # Attempt to open serial port.
        try:
            self.ser = serial.Serial(port=port,
                                     baudrate=115200,
                                     timeout=2,
                                     write_timeout=2)
            # Timeout is set, so reading from serial port may return less
            # characters than requested. With no timeout, it will block until
            # the requested number of bytes are read (eg. ser.read(10)).
            # Note: timeout does not seem to apply to read() (read one byte) or
            #       readline() (read '\n' terminated line). Perhaps need to
            #       implement own timeout in read function...
        except serial.SerialException:
            logging.warning('No serial device detected.')

        # Give microcontroller time to startup (esp. if has bootloader on it)
        sleep(2)

        # Flush input buffer (discard all contents) just in case
        self.ser.reset_input_buffer()

    def run(self):
        # Keep looping until 'None' sentinel is received on the command queue
        for command in iter(self.command_queue.get, None):
            logging.debug('Received command in queue: %s', command)

            # Send command to microcontroller
            self.send_command(command)

            # sleep(0.3)  # debugging empty response issue. shouldn't need this

            # Read in response from microcontroller
            # response = self.get_response()  # unreliable
            response = self.get_response_until()  # may block forever

            #  Send response back to client
            self.response_queue.put(response)
            # Tell queue that the job is done
            self.command_queue.task_done()

    def read_byte(self):
        '''
        Read one byte from serial port.
        '''
        try:
            read_byte = self.ser.read(1)
        except serial.SerialException:
            # Attempted to read from closed port
            logging.error('Serial port not open - unable to read.')
        return read_byte

    def get_response_until(self):
        '''
        Read from serial input buffer until end_flag byte is received.
        Note: for some reason pyserial's timeout doesn't work on these read
              commands (tested on Windows and Linux), so this may block forever
              if microcontroller doesn't response for whatever reason.
        '''
        recvd_command = b''
        while True:
            in_byte = self.ser.read(size=1)
            recvd_command = recvd_command + in_byte
            if in_byte == self.eolchar:
                break
        return recvd_command

    def get_response(self):
        '''
        Read in microcontroller response from serial input buffer.
        Note: have been having issues with in_waiting either returning 0 bytes
              but still being able to read using something like read(10), or
              in_waiting returning 0 bytes due to returning too fast before
              the microcontroller can respond.
        '''

        recvd_command = b''
        # Save value rather than calling in_waiting in the while loop, otherwise
        # will also receive the responses for other commands sent while
        # processing the original command
        bytes_waiting = self.ser.in_waiting
        logging.debug('Bytes in serial input buffer: %s', bytes_waiting)
        while bytes_waiting > 0:
            recvd_command = recvd_command + self.ser.read(size=1)
            bytes_waiting = bytes_waiting - 1
        return recvd_command


    def send_command(self, command):
        '''Send commands to microcontroller via RS232.
        This function deals directly with the serial port.
        '''

        # Attempt to write to serial port.
        try:
            self.ser.write(command)
        except serial.SerialTimeoutException:
            # Write timeout for port exceeded (only if timeout is set).
            logging.warning('Serial port timeout exceeded - unable to write.')
        except serial.SerialException:
            # Attempted to write to closed port
            logging.warning('Serial port not open - unable to write.')

        # Wait until all data is written
        self.ser.flush()

        logging.info('Command sent to microcontroller: %s', command)

    def close(self):
        ''' Close connection to the serial port.'''
        self.ser.close()
