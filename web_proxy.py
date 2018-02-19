import sys
import socket
import traceback
import threading
import select
import os
from console import Management_Console, parse_http
from beaker.cache import CacheManager
from beaker.util import parse_cache_config_options
import re
import time

cache_opts = {
    'cache.type': 'file',
    'cache.data_dir': '/tmp/cache/data',
    'cache.lock_dir': '/tmp/cache/lock'
}

class Proxy:

    MAX_CONNECTIONS = 200
    MAX_BUFFER = 4096
    CACH_DIR = './cache'

    DEFAULT_MAX_AGE = 60 #1 minute
    HTTP_403 = b'HTTP/1.1 403 Forbidden OK\r\n\r\n<h1>403 Error</h1><p>Website blocked by Proxy</p>'
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
            cache = CacheManager(**parse_cache_config_options(cache_opts))
            self.cache = cache.get_cache('mytemplate', type='file', expire=5)
            self.m_cache = {}

            print(" Initializing socket")
            print(" Proxy listening on port {}".format(port))

            self.connections = []
            self.console = Management_Console()

        except Exception as e:
            if self.browser_s:
                self.browser_s.close()
            print(" Unable to init socket: \n{}\n{}".format(e, e.with_traceback))
            print(traceback.format_exc())
            sys.exit(2)


    def handle_connection(self, connection, address):
        try:
            request = connection.recv(self.MAX_BUFFER)
            server, port, url = self.parse_request(request)
            if self.console.is_blocked(server):
                connection.send(self.HTTP_403)
                connection.close()
            elif request not in self.connections:
                cached = self.is_cached(url)
                c = True if cached else False
                print("[{}:{}] CACHED = {}".format(url, port, c))
                #print(self.m_cache.keys())
                if cached:
                    self.log("N~[{}] Cached~ ".format(url.decode('utf-8', 'ignore')), 1)
                    connection.send(cached)
                    connection.close()
                    self.log("C~[{}]~EXIT connection".format(url.decode('utf-8', 'ignore')), 1)
                else:
                    print('init')
                    self.connections.append(url)
                    t = threading.Thread(target=self.connect, args=(connection, address, request))
                    t.setDaemon(True)
                    t.start()
        except Exception as e:
            if connection:
                connection.close()
            #print(e)
            #print(traceback.format_exception)

    def start(self):
        self.c_thread = threading.Thread(target=self.console.start, args=())
        self.c_thread.setDaemon(True)
        self.c_thread.start()

        while 1:
            print(self.m_cache.keys())
            print(self.connections)
            connection, address = self.browser_s.accept()
            self.handle_connection(connection, address)

        self.browser_s.close()


    def connect(self, connection, addr, request):
        org_req = request
        #cached = self.m_cache.get(request ,b'')

        try:
            server, port, url = self.parse_request(request)
            url_d = url.decode('utf-8')
            https = request[:7] == b'CONNECT'

            print('[{}:{}] Creating new connection'.format(server, port))
            self.log('N~[{}]~Creating new connection'.format(url_d), 1)

            server_s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            if https: #tunnel connection
                connection.send(self.HTTP_200)
                request = connection.recv(self.MAX_BUFFER)
                print(" Tunneled")

            server_s = socket.create_connection((server, port))

            self.log('F~{}~ '.format(request.decode('utf-8', 'ignore')), 3)
            #print("[{}:{}] SEND Request: {}".format(server, port, request))

            server_s.sendall(request)
            alive = True
            while alive:
                read, x, y = select.select([connection, server_s], [], [])

                for sock in read:
                    data = sock.recv(self.MAX_BUFFER)
                    if(len(data)>0):
                        if sock == server_s:
                            connection.sendall(data)
                            self.log('R~{}~ '.format(data.decode('utf-8', 'ignore')), 3)
                            if not https:
                                header = parse_http(data)
                                print("[{}] {}".format(url, header.get(b'Cache-Control', b'')))
                                #srv = "[{}]".format(url)
                                self.write_to_cache(url, data, header)
                        else:
                            server_s.sendall(data)
                            self.log('F~{}~ '.format(data.decode('utf-8', 'ignore')), 3)
                    # if disconnect signal exit
                    else:
                        alive = False
                        break # need another break???

            self.log("C~[{}]~EXIT connection".format(url.decode('utf-8','ignore')), 1)
            print("[{}:{}] EXIT connection".format(url.decode('utf-8'), port))
            self.close_cache(url)
            server_s.close()
            connection.close()
            self.connections.remove(url)

        except Exception as e:
            print(traceback.format_exc())


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


    def parse_c_control(self, c_control):
        max_age = self.DEFAULT_MAX_AGE
        cachable = not (b'no-store' in c_control or b'no-cache' in c_control)
        parts = c_control.split(b',')
        for part in parts:
            if b'max-age' in part:
                max_age = int(part.split(b'=')[1])

        return max_age, cachable

    def close_cache(self, request):
        print("{} closed".format(request))
        if self.is_cached(request):
            self.m_cache[request][1] = False

    def write_to_cache(self, key, data, header):
        c_control = header.get(b'Cache-Control', b'')
        etag = header.get(b'ETag', None)
        max_age, cachable = self.parse_c_control(c_control)
        if  cachable and max_age > 0:
            print("caching ... \n{}".format(''))
            if self.is_cached(key) and self.m_cache[key][1]:
                self.m_cache[key][0] += data
            else:
                self.m_cache[key] = [data, True, time.time()+max_age, etag]

    def is_cached(self, request):
        res = self.m_cache.get(request, (None, None, 0, None))
        if res[2] >= time.time():
            return res[0]
        #TODO clear entry
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

    def close(self):
        if self.browser_s:
            self.browser_s.close()
            self.console.close()


if __name__ == '__main__':
    port = 8002
    logging = 1

    try:
        if len(sys.argv) == 3:
            logging = int(sys.argv[2])
        if len(sys.argv) >= 2:
            port = int(sys.argv[1])
    except Exception as e:
        print("Can't parse args: {}".format(e))

    proxy = Proxy('localhost', port, logging=logging)
    try:
        proxy.start()
    except KeyboardInterrupt:
        proxy.close()
        print('\nShutting proxy down')
        sys.exit(1)
