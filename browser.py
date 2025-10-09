import socket
import ssl
'''
This rudimentary python implementation of a web browser can:
    - parse a URL into a scheme, host, port, and path;
    - connect to that host using the socket and ssl libraries;
    - send an HTTP request to that host, including a Host header;
    - split the HTTP response into a status line, headers, and a body;
    - print the text (and not the tags) in the body.
As guided by Web Browser Engineering by Pavel Panchekha & Chris Harrelson
'''
class URL:
    def __init__(self, url):
        # [scheme][hostname][path]
        self.scheme, url = url.split("://", 1)
        assert self.scheme in ["http", "https"]  # detect scheme
        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443

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

        # Request to server, send method
        request = "GET {} HTTP/1.0\r\n".format(self.path)
        request += "Host: {}\r\n".format(self.host)
        request += "\r\n"
        s.send(request.encode("utf8"))
        
        # Read server response
        response = s.makefile("r", encoding="utf8", newline="\r\n")
        statusline = response.readline()  # first line, status line
        version, status, explanation = statusline.split(" ", 2)
        response_headers = {}
        while True:
            line = response.readline()  # next, headers
            if line == "\r\n": break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()
            
        # block unusual data behavior
        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        # access data after headers
        content = response.read()
        s.close()  # close socket

        # display body
        return content

def show(body):
    # Skip tags in text
    in_tag = False
    for c in body:
        if c =="<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            print(c, end="")

def load(url):
    # load page, request and show
    body = url.request()
    show(body)

if __name__ == "__main__":
    import sys
    load(URL(sys.argv[1]))