import socket
import threading
import traceback
import hashlib
import base64
import os
import json
import struct
import array


'''
returns dictionaty for the headers
   where the keys are the header names and their data is the data
'''
def parse_http(data):
    headers = {}
    lines = data.split(b'\r\n')
    for line in lines:
        parts = line.split(b': ', 1)
        if len(parts) == 2:
            headers[parts[0]] = parts[1]
    return headers

class Websocket:

    MAX_CONNECTIONS = 1
    MAX_BUFFER = 1024
    GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
    HANDSHAKE_STR = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: WebSocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Accept: {accept}\r\n\r\n"
    )

    '''
    Initialise socket to listen on
    '''
    def __init__(self, host, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', port))
        self.sock.listen(self.MAX_CONNECTIONS)

    '''
    listen and connect to requests
        only one connection to web console!
    '''
    def start(self):
        while 1:
            self.conn, self.addr = self.sock.accept()
            self.connect()

    '''
    sudo connect (overwritten by management console)
    '''
    def connect(self):
        try:
            self.handshake()
            while 1:
                data = self.unpack(self.conn)
                if data:
                    self.conn.send(self.pack(data))
                else:
                    break
            self.conn.close()

        except Exception as e:
            pass

    #close socket
    def close(self):
        if self.sock:
            self.sock.close()

    '''
    send a handshake to the connection
    '''
    def handshake(self):
        print('WS handshake ...', end=' ')
        data = self.conn.recv(self.MAX_BUFFER)
        headers = parse_http(data)
        accept = self.hash(headers[b'Sec-WebSocket-Key'])

        header = self.HANDSHAKE_STR.format(accept=accept)
        header = header.encode()
        self.conn.send(header)
        print('Done')

    '''
    hash the websocket-key (for handshake)
    '''
    def hash(self, key):
        key = key.decode('utf-8')
        sha1 = hashlib.sha1((key + self.GUID).encode()).digest()
        return base64.b64encode(sha1).decode()

    '''
    encode/pack data according to websocket protocol
    '''
    def pack(self, data, fin=1, opcode=1):
        if fin > 0x1:
            raise ValueError('FIN bit parameter must be 0 or 1')
        if 0x3 <= opcode <= 0x7 or 0xB <= opcode:
            raise ValueError('Opcode cannot be a reserved opcode')
        try:
            header = struct.pack('!B', ((fin << 7)|(0 << 6)|(0 << 5)|(0 << 4)|opcode))
            mask_bit = 0
            length = len(data)
            if length < 126:
                header += struct.pack('!B', (mask_bit | length))
            elif length < (1 << 16):
                header += struct.pack('!B', (mask_bit | 126)) + \
                          struct.pack('!H', length)
            elif length < (1 << 63):
                header += struct.pack('!B', (mask_bit | 127)) + \
                          struct.pack('!Q', length)

            body = data.encode()
            return bytes(header+body)

        except Exception as e:
            pass

    '''
    unpack/decode data according to websocket protocol
    '''
    def unpack(self, client):
        try:
            data = client.recv(2)
            head1, head2 = struct.unpack('!BB', data)
            fin = bool(head1 & 0b10000000)
            opcode = head1 & 0b00001111
            if opcode == 1:
                length = head2 & 0b01111111
                if length == 126:
                    data = client.recv(2)
                    length, = struct.unpack('!H', data)
                elif length == 127:
                    data = client.recv(8)
                    length, = struct.unpack('!Q', data)

            mask_bits = client.recv(4)
            mask_bits = bytearray(mask_bits)
            data = client.recv(length)
            data = bytearray(data)
            DECODED = []
            for i in range(0, len(data)):
                DECODED.append(data[i] ^ mask_bits[i % 4])
            DECODED = array.array('B', DECODED).tostring()
            if fin:
                return DECODED
        except Exception as e:
            return None


class Management_Console(Websocket):

    BLACKLIST_F = 'bl.txt'

    '''
    Initialise Console
       init websocket connection
       load blacklist (if saved)
    '''
    def __init__(self):
        super().__init__('', 8008)
        self.conn = None
        print('Management Console listening on {}'.format(8008))
        self.blacklist = {}
        if os.path.isfile(self.BLACKLIST_F):
            self.blacklist = json.load(open(self.BLACKLIST_F, 'r'))

    '''
    Connect to web console
        only listens for data from the web console
        the log function is used to send data to it.
    '''
    def connect(self):
        try:
            self.handshake()
            self.log("B~"+'\n'.join(self.blacklist.keys())+'~ ')
            while 1:
                data = self.unpack(self.conn)
                if data:
                    # add to blacklist
                    self.blacklist[data.decode('utf-8')] = ''
                else:
                    break
            print("CLOSING!!!")
            self.conn.close()

        except Exception as e:
            pass

    '''
    Log/send data to the web console over socket connection
    '''
    def log(self, data):
        try:
            d = self.pack(data)
            self.conn.send(d)
        except Exception as e:
            pass

    '''
    Return if the url is on the blacklist (blocked)
    '''
    def is_blocked(self, url):
        url = url.decode('utf-8')
        for domain in self.blacklist:
            if domain in url:
                return True
        return False

    '''
    close console - close socket, save blacklist
    '''
    def close(self):
        #save blacklist
        json.dump(self.blacklist, open(self.BLACKLIST_F, 'w'))
        self.sock.close()
        #close socket


if __name__ == '__main__':
    Management_Console().start()
