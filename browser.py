import socket
import ssl
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
'    # TODO: Caching
'    # TODO: Compression
'''

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

    def request(self):

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
            
        # block unusual data behavior
        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers
        
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

        # Read only as many bytes as given in Content-Length header
        try:
            con_len = int(response_headers.get("content-length", 0))
            content = response.read(con_len)
        except:
            raise ValueError("Content-Length header missing in response")
        
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