import socket
import ssl
import time
import gzip
from pathlib import Path
from urllib.parse import urljoin

'''
' This rudimentary python implementation of a web browser can:
'    - parse a URL into a scheme, host, port, and path;
'    - connect to that host using the socket and ssl libraries;
'    - send an HTTP request to that host, including a Host header;
'    - split the HTTP response into a status line, headers, and a body;
'    - print the text (and not the tags) in the body.
' As guided by Web Browser Engineering by Pavel Panchekha & Chris Harrelson
' Updated functionality by me:
'    - HTTP/1.1
'    - File URLs and default home page
'    - 'data:' scheme (text/HTML)
'    - Convert Entities (&lt; and &gt;)
'    - 'view-source:' scheme (show tags)
'    - Keep-alive connection and reuse socket repeat requests
'    - Redirects: Error Code 300's handled
'    - Caching: Cache-Control support for no-store and max-age vals
'    - Compression: supports encoding headers and compression
'''
cache = {}

class URL:
    def __init__(self, url):
        self.saved_socket = None
        self.num_redirects = 0
        # [scheme][hostname][path]
        try:
            # check for data scheme
            if url.startswith("data:"):
                self.scheme, url = url.split(":", 1)
            else:
                self.scheme, url = url.split("://", 1)
        # Catch url/filepath format issues    
        except ValueError:   
            print("Value Error:")
            print("Please Review Url or File Path Format, must include '://'.")
            sys.exit(1)
        assert self.scheme in ["http", "https", "file", "data", "view-source:http", "view-source:https"]  # detect scheme
        
        if self.scheme == "http" or self.scheme == "view-source:http":
            self.port = 80
        elif self.scheme == "https" or self.scheme == "view-source:https":
            self.port = 443
        elif self.scheme == "data":
            mime_type, data_sch_content = url.split(",", 1)
            # only support text/html so far
            if mime_type != "text/html":
                print("This MIME type is currently unsupported.")
                sys.exit(1)
            print(data_sch_content)
            sys.exit(0)
        elif self.scheme == "file":

            # Handle file search
            try:
                if url[0] == '/':
                    file_path = "~" + url
                else:
                    file_path = "~/" + url
                abs_path = Path(file_path).expanduser()
                if abs_path.is_file():
                    with open(abs_path, 'r') as file:
                        content = file.read()
                        print(content)
                sys.exit(0)
            except FileNotFoundError:
                print(f'Error: Requested file {url} was not found.')
                sys.exit(1)

        # Separate host from path
        if '/' not in url:
            url = url + '/'
        self.host, url = url.split('/', 1)
        self.path = '/' + url

        #  Check for and parse port
        if ':' in self.host:
            self.host, port = self.host.split(':', 1)
            self.port = int(port)

        # set cache key
        self.cache_key = f"{self.scheme}://{self.host}:{self.port}{self.path}"

    def request(self):
        # check cache before request
        if self.cache_key in cache:
            cached = cache[self.cache_key]
            age = time.time() - cached["stored"]
            # use cache if exists and not expired
            if age < cached["max_age"]:
                print("Using cached")
                return cached["content"]
            else:
                print("deleting")
                del cache[self.cache_key]  # max age reached, clear cache
            
        if self.saved_socket is None:
            # Create Socket
            s = socket.socket(
                family=socket.AF_INET,  # how to find other comp
                type=socket.SOCK_STREAM,  # each comp send arbitrary amt data
                proto=socket.IPPROTO_TCP,  # steps comps establish connection
            )

            # Connect socket
            s.connect((self.host, self.port))  # (host, port)
            if self.scheme == "https":  # encrypt connection
                ctx = ssl.create_default_context()  # create context
                s = ctx.wrap_socket(s, server_hostname=self.host)  # wrap socket
            s.settimeout(10)
            self.saved_socket = s
        else:
            # Use Saved Socket
            s = self.saved_socket

        # Request to server, send method
        request = "GET {} HTTP/1.1\r\n".format(self.path)
        request += "Host: {}\r\n".format(self.host)
        request += "Connection: {}\r\n".format("keep-alive")
        request += "Accept-Encoding: {}\r\n".format("gzip")
        request += "User-Agent: {}\r\n".format("PyBrowse")
        request += "\r\n"
        s.send(request.encode("utf8"))
        
        # Read server response
        response = s.makefile("rb", newline=b"\r\n")
        statusline = response.readline()  # first line, status line
        statusline = statusline.decode("utf8")
        version, status, explanation = statusline.split(" ", 2)
        print(f'status: {status}')
        
        response_headers = {}
        while True:
            line = response.readline()  # next, headers
            if line == b"\r\n": break
            line = line.decode("utf8").strip()
            if ":" in line:
                header, value = line.split(":", 1)
                response_headers[header.casefold()] = value.strip()
            
        # Check for and handle Error code 300 redirects
        if int(status) > 299 and int(status) < 400:
            location = response_headers['location']

            if not location:
                raise ValueError("Redirect Error, response does not provide 'location'")
            
            # Handle incomplete urls
            full_url = urljoin(f"{self.scheme}://{self.host}{self.path}", location)

            # set limit for allowable redirects
            if self.num_redirects >= 5:
                raise Exception("Too many redirects. Please check url")

            # process new url and return new location
            redirect = URL(full_url)
            redirect.num_redirects = self.num_redirects + 1
            return redirect.request()

        # Read based on encoding provided
        transfer_encoding = response_headers.get('transfer-encoding', '').lower()
        content_encoding = response_headers.get('content-encoding', '').lower()

        # Read by chunks 
        if "chunked" in transfer_encoding:
            content = b""
            while True:
                line = response.readline()
                chunk_size = int(line.strip(), 16)
                if chunk_size == 0:
                    break
                chunk = response.read(chunk_size)
                content += chunk
                response.read(2) #  for \r\n
            # discard trailing headers
            while True:
                line = response.readline()
                if line == b"\r\n":
                    break
        # Read only as many bytes as given in content-length header
        elif "content-length" in response_headers:
            con_len = int(response_headers.get("content-length"))
            content = response.read(con_len)
        # content length / transfer encoding not provided, read as is
        else:
            content = response.read()

        # Handle and decompress g-zip encoding
        if 'gzip' in content_encoding:
            try:
                print("decompressed")
                content = gzip.decompress(content)
            except Exception as e:
                raise ValueError(f'Failed to decompress gzip: {e}')

        # Check if cachable allowed
        is_cachable = False
        max_age = None
        cache_control = response_headers.get('cache-control', '').lower()
        
        if "no-store" in cache_control:
            is_cachable = False  # don't cache
        elif "max-age=" in cache_control:
            try:
                is_cachable = True
                max_age = int(cache_control.split("max-age=", 1)[1].split(',')[0].strip())
                print(f'max-age:{max_age}')
            except ValueError:
                pass
        
        if is_cachable:
            cache[self.cache_key] = {
                "stored": time.time(),
                "max_age": max_age,
                "content": content
            }
            print("Cached")
        
        # display body
        return content

def show(body):
    # Don't skip tags if view-source
    if sys.argv[1].startswith("view-source"):
        print(body)
        sys.exit(0)
    # Skip tags in text
    full_c = ""
    in_tag = False
    for c in body:
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            full_c += c
    # Entities gt and lt converted
    full_c = full_c.replace("&lt;", "<")
    full_c = full_c.replace("&gt;", ">")
    print(full_c)

def load(url):
    # load page, request and show
    body = url.request()
    show(body.decode("utf8"))

if __name__ == "__main__":
    import sys
    args = len(sys.argv)
    # if no search value, return home page
    if args < 2:
        # Home page if no queries/ initial open
        with open('home.txt', 'r') as file:
            content = file.read()
            print(content)        
    if args == 2:
        # Standard Query, filepaths and urls
        load(URL(sys.argv[1]))
    if args > 2:
        # Data schema content space useage is giving extra args
        if sys.argv[1].startswith("data:"):
            list_args = sys.argv[1:]
            data_query_str = " ".join(list_args)
            load(URL(data_query_str))