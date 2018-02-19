import socket
import threading
import traceback
import hashlib
import base64
import os
import json
import struct
import array

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

    def __init__(self, host, port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('', port))
        self.sock.listen(self.MAX_CONNECTIONS)

    def start(self):
        while 1:
            self.conn, self.addr = self.sock.accept()
            # print('Management Console connected')
            self.connect()
            #request = connection.recv(self.MAX_BUFFER)

    def connect(self):
        try:
            self.handshake()
            while 1:
                data = self.unpack(self.conn)
                #print(data)
                if data:
                    #print(data.decode('utf-8', 'ignore'))
                    #print("ECHO")
                    #add to black list
                    test = b"HELLO"
                    self.conn.send(self.pack(test))
                else:
                    break
            #print("CLOSING!!!")
            self.conn.close()

        # except socket.error as e:
        #     if self.sock:
        #         self.sock.close()
        #     if self.conn:
        #         self.conn.close()
        #     print(e)
        #     sys.exit(1)
        except Exception as e:
            print(traceback.format_exc())

    def close(self):
        if self.sock:
            self.sock.close()

    def handshake(self):
        print('WS handshake ...', end=' ')
        data = self.conn.recv(self.MAX_BUFFER)
        #print(data)
        headers = parse_http(data)
        accept = self.hash(headers[b'Sec-WebSocket-Key'])

        header = self.HANDSHAKE_STR.format(accept=accept)
        header = header.encode()
        #print(header)
        self.conn.send(header)
        print('Done')
        #convert to bytes

    def hash(self, key):
        key = key.decode('utf-8')
        sha1 = hashlib.sha1((key + self.GUID).encode()).digest()
        return base64.b64encode(sha1).decode()

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
                header += struct.pack('!B', (mask_bit | 126)) + struct.pack('!H', length)
            elif length < (1 << 63):
                header += struct.pack('!B', (mask_bit | 127)) + struct.pack('!Q', length)

            body = data.encode()
            return bytes(header+body)

        except Exception as e:
            print(traceback.format_exc())

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
            err = e.args[0]
            # this next if/else is a bit redundant, but illustrates how the
            # timeout exception is setup
            if err == 'timed out':
                pass
            elif err == 10053:
                return None
            else:
                print(e)
                print(e.__traceback__)
                print(e.with_traceback)
                return None


class Management_Console(Websocket):

    BLACKLIST_F = 'bl.txt'

    def __init__(self):
        super().__init__('', 8008)
        self.conn = None
        print('Management Console listening on {}'.format(8008))
        self.blacklist = {}
        if os.path.isfile(self.BLACKLIST_F):
            self.blacklist = json.load(open(self.BLACKLIST_F, 'r'))

    def connect(self):
        try:
            self.handshake()
            self.log("B~"+'\n'.join(self.blacklist.keys())+'~ ')
            while 1:
                data = self.unpack(self.conn)
                #print(data)
                if data:
                    self.blacklist[data.decode('utf-8')] = ''
                    #add to black list
                    #self.conn.send(self.pack(test))
                else:
                    break
            print("CLOSING!!!")
            self.conn.close()

        # except socket.error as e:
        #     if self.sock:
        #         self.sock.close()
        #     if self.conn:
        #         self.conn.close()
        #     print(e)
        #     sys.exit(1)
        except Exception as e:
            print(traceback.format_exc())

    def log(self, data):
        try:
            #print(self.conn)
            d = self.pack(data)
            self.conn.send(d)
        except Exception as e:
            print("Can't send data: {}".format(e))

    def is_blocked(self, url):
        url = url.decode('utf-8')
        for domain in self.blacklist:
            if domain in url:
                return True
        return False

    def close(self):
        #save blacklist
        json.dump(self.blacklist, open(self.BLACKLIST_F, 'w'))
        self.sock.close()
        #close socket


if __name__ == '__main__':
    Management_Console().start()
