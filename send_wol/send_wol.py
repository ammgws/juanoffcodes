#!/usr/bin/env python3
"""
Send a WOL magic packet. Works on both Linux and Windows.

@author: ammgws
"""
from socket import socket, AF_INET, SOCK_DGRAM, SOL_SOCKET, SO_BROADCAST

def send_magic_packet(mac_address, broadcast_address, port=9):
    ''' Send a WOL magic packet for the specified MAC address'''
    # Create an IPv4, UDP socket
    sock = socket(family=AF_INET, type=SOCK_DGRAM)
    # Enable sending datagrams to broadcast addresses
    sock.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)
    # Build magic packet
    mac_address = bytes.fromhex(mac_address.replace(':', ''))
    magic_packet = b'\xFF' * 6 + mac_address * 16
    # Send magic packet
    result = sock.sendto(magic_packet, (broadcast_address, port))
    # Success: sent all 102 bytes of the magic packet
    if result == len(magic_packet):
        ack = 'ACK'
    # Fail: not all bytes were sent
    else:
        ack = 'NAK'
    return ack

def main():
    result = send_magic_packet('xx:xx:xx:xx:xx:xx', 'xx.xx.xx.xx')
    print(result)

if __name__ == '__main__':
    main()
