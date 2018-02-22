import sys
import socket
import traceback
import threading
import select
import os
from console import Management_Console, parse_http
import re
import time

class Proxy:

    MAX_CONNECTIONS = 5 #max connections for listening socket
    MAX_BUFFER = 4096 #max buffer to be received over connection
    CACH_DIR = './cache'

    DEFAULT_MAX_AGE = 60 #1 minute
    HTTP_403 = b'HTTP/1.1 403 Forbidden OK\r\n\r\n' + \
               b'<h1>403 Error</h1><p>Website blocked by Proxy</p>'
    HTTP_200 = b'HTTP/1.1 200 OK\r\n\r\n'

    '''
    Initialise Proxy
    browser_s -> socket listening on for browser requests
    logging -> verbosity of management console logs
    m_chache -> cache for http responses
    connections -> list of current connections (stores url)
    console -> Management console
    '''
    def __init__(self, host, port, logging=1):
        try:
            self.browser_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.browser_s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.browser_s.bind((host, port))
            self.browser_s.listen(self.MAX_CONNECTIONS)

            self.logging = logging
            self.m_cache = {}

            print(" Initializing socket")
            print(" Proxy listening on port {}".format(port))

            self.connections = []
            self.console = Management_Console()

        except Exception as e:
            if self.browser_s:
                self.browser_s.close()
            print(" Unable to init socket: \n{}\n{}".format(e, e.with_traceback))
            sys.exit(2)

    '''
    Start proxy - start console
    listen for connections (from browser)
    '''
    def start(self):
        self.c_thread = threading.Thread(target=self.console.start, args=())
        self.c_thread.setDaemon(True)
        self.c_thread.start()

        while 1:
            connection, address = self.browser_s.accept()
            # handler creates thread for connection if requiered
            self.handle_connection(connection, address)
        self.browser_s.close()

    '''
    Check if connection is valid (not blocked)
    Check if request is cached
    Else create thread for connection
    '''
    def handle_connection(self, connection, address):
        try:
            request = connection.recv(self.MAX_BUFFER)
            server, port, url = self.parse_request(request)
            url_d = url.decode('utf-8', 'ignore')
            #CHECK IF BLOCKED
            if self.console.is_blocked(server):
                connection.send(self.HTTP_403)
                connection.close()
            elif request not in self.connections:
                #CHECK IF CACHED
                cached = self.is_cached(url)
                if cached:
                    self.log("N~[{}] Cached~{}".format(url_d, time.ctime()[10:19]), 1)
                    for i in cached:
                        connection.sendall(i)
                    connection.close()
                    self.log("C~[{}]~{}".format(url_d, time.ctime()[10:19]), 1)
                #ELSE MAKE THREAD
                else:
                    self.connections.append(url)
                    t = threading.Thread(target=self.connect, \
                                         args=(connection, address, request))
                    #daemon: don't have to wait for thread to close on interupt
                    t.setDaemon(True)
                    t.start()
        except Exception as e:
            if connection:
                connection.close()

    '''
    Establish socket connection (tunnel https and wss)
    Listen on both connection and server_s for connection
    connection - socket to browser
    server_s - socket to server
    '''
    def connect(self, connection, addr, request):
        try:
            server, port, url = self.parse_request(request)
            url_d = url.decode('utf-8')
            https = request[:7] == b'CONNECT' #needs tunneling
            initial_req = True
            alive = True

            print('[{}:{}] Creating new connection'.format(server, port))
            self.log('N~[{}]~{}'.format(url_d, time.ctime()[10:19]), 1)
            server_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            if https: #tunnel connection on CONNECT
                connection.send(self.HTTP_200)
                request = connection.recv(self.MAX_BUFFER)
                print(" Tunneled")

            server_s = socket.create_connection((server, port))

            self.log('F~{}~ '.format(request.decode('utf-8', 'ignore')), 3)
            # get 1st time for bandwidth (before data send)
            t1 = time.time()
            server_s.sendall(request)

            while alive:
                # select returns sockets ready for reading
                # means no extra thread for listening both ways
                read, x, y = select.select([connection, server_s], [], [])

                for sock in read:
                    data = sock.recv(self.MAX_BUFFER)
                    # if valid data
                    if(len(data)>0):
                        # if data from server send to browser
                        if sock == server_s:
                            connection.sendall(data)
                            if initial_req: # log bandwidth on initial respnose
                                t2 = time.time()
                                bandw = round((self.MAX_BUFFER*0.001) / (t2-t1), 3)
                                self.log('W~{}~{} K/sec'.format(url_d, bandw), 1)
                                initial_req = False
                            if not https: # attempt to CACHE if http
                                header = parse_http(data)
                                self.handle_cache(url, data, header)
                            self.log('R~{}~ '.format(data.decode('utf-8', 'ignore')), 3)
                        # if data from browser send to server
                        else:
                            server_s.sendall(data)
                            self.log('F~{}~ '.format(data.decode('utf-8', 'ignore')), 3)
                    # if disconnect signal exit
                    else:
                        alive = False
                        break

            self.log("C~[{}]~{}".format(url_d, time.ctime()[10:19]), 1)
            print("[{}:{}] EXIT connection".format(url.decode('utf-8'), port))
            self.close_cache(url)
            server_s.close()
            connection.close()
            self.connections.remove(url)

        except Exception as e:
            #print(traceback.format_exc())
            pass

    '''
    Get server, port and url from request
    '''
    def parse_request(self, request):
        try:
            url = (request.split(b'\r\n')[0]).split(b' ')[1]

            http_pos = url.find(b'://')
            temp = url if http_pos == -1 else url[(http_pos+3):]
            port_pos = temp.find(b':')
            server_pos = temp.find(b'/')
            if server_pos == -1:
                server_pos = len(temp)
            server = ''
            port = -1
            if port_pos==-1 or server_pos < port_pos:
                port = 80 #default port
                server = temp[:server_pos]
            else:
                port = int((temp[(port_pos+1):])[:server_pos-port_pos-1])
                server = temp[:port_pos]

            return server, port, url
        except Exception as e:
            print("Parse error: {}".format(request))

    '''
    Parse cache-controle: max-age & if it is cachable
    '''
    def parse_c_control(self, c_control):
        max_age = self.DEFAULT_MAX_AGE
        cachable = not (b'no-store' in c_control or b'no-cache' in c_control)
        parts = c_control.split(b',')
        for part in parts:
            if b'max-age' in part:
                max_age = int(part.split(b'=')[1])

        return max_age, cachable

    '''
    "close"-cache on http disconnect
    '''
    def close_cache(self, request):
        print("{} closed".format(request))
        if self.is_cached(request):
            self.m_cache[request][1] = False

    '''
    write data to cache if cachable
    '''
    def handle_cache(self, key, data, header):
        c_control = header.get(b'Cache-Control', b'')
        etag = header.get(b'ETag', None)
        max_age, cachable = self.parse_c_control(c_control)
        if cachable and max_age > 0:
            print("caching ... ")
            #if multiple respnoses append until close
            if self.is_cached(key) and self.m_cache[key][1]:
                self.m_cache[key][0].append(data)
            else:
                # store first response, timeout and etag
                self.m_cache[key] = [[data], True, time.time()+max_age, etag]

    '''
    Checks if item is cached and uptodate
    returns response else None
    '''
    def is_cached(self, key):
        res = self.m_cache.get(key, (None, None, 0, None))
        if res[2] >= time.time():
            return res[0]
        #check with e tag
        return None


    '''
    Log message to management console
        (level is for debug/verbosity)
    '''
    def log(self, message, level):
        if level <= self.logging:
            if isinstance(message, str):
                self.console.log(str(message))
            else:
                self.console.log(message.decode())

    '''
    Close proxy and console
    '''
    def close(self):
        if self.browser_s:
            self.browser_s.close()
            self.console.close()


if __name__ == '__main__':
    port = 8002
    logging = 1

    # get port and logging option if set
    try:
        if len(sys.argv) == 3:
            logging = int(sys.argv[2])
        if len(sys.argv) >= 2:
            port = int(sys.argv[1])
    except Exception as e:
        print("Can't parse args: {}".format(e))

    # start proxy
    proxy = Proxy('localhost', port, logging=logging)
    try:
        proxy.start()
    except KeyboardInterrupt:
        proxy.close()
        print('\nShutting proxy down')
        sys.exit(1)
