###webserver---采用wsgi协议
import socket
import sys
import datetime
import errno

class WSGIServer(object):
    def __init__(self):
        self.serverName = None
        self.serverPort = None
        self.responseHeader = None
        self.requestData = None
        self.application = None
        self.clientConnection = None
        self.requestMethod = None
        self.path = None
        self.requestVersion = None

    def startResponse(self, status, header, exc_info=None):
        """
        回调函数callback，获取响应状态和响应头信息
        在接受到请求的时候，作为回调函数传送给后台逻辑代码（如框架类）
        具体操作application(env, startResponse)
        env为具体的环境变量
        当web程序执行完毕，回调startResponse(),返回相应信息给web程序

        :param status: 处理状态码  比如404   200 等
        :param header: 头部信息
        :param exc_info: 执行结果信息
        """

        #设置基本的服务器头部信息
        serverHeader = [
            ('Date', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            ('Server', "SanJay's WSGIServer v1.0")
        ]
        #设置响应码，并把两种头部信息相加
        self.responseHeader = [status, header + serverHeader]


    def finishResponse(self, result):
        """
        对发起的请求进行响应
        函数只是对返回的内容进行格式化处理
        :param result:返回的结果信息
        :return:
        """
        try:
            status, headers = self.responseHeader
            response = 'HTTP/1.1 {status}\r\n'.format(status=status)
            for header in headers:
                response += '{0}: {1}\r'.format(*header)
            response += '\r\n'
            for data in result:
                response += data
            print(''.join(
                '> {line}\n'.format(line=line) for line in response.splitlines()
            ))
            self.clientConnection.sendall(response)
        finally:
            self.clientConnection.close()

    def handleRequest(self, connection):
        """
        当接受到请求时，调用
        :param connection: 客户端链接
        :return:
        """
        #客户端发起的请求
        self.requestData = self.clientConnection.recv(1024)
        #分解请求信息，将信息提取出来
        self.parseRequest()
        #配置环境信息
        env = self.getEnviron()
        #配置完成信息之后，需要向后台的web程序发起处理请求了
        result = self.application(env, self.startResponse)
        #请求，获取返回信息后，可以反馈给客户端啦
        self.finishResponse(result)

    def parseRequest(self):
        """
        对requestData进行分解
        从而设置请求方式 method  -- get/post,,,,
        请求路径path  --  对应的文件路径，很必要
        请求的版本   --- http 1.1
        """
        requestData = self.requestData
        requestLine = requestData.splitlines()[0]
        requestLine = requestLine.rstrip('\r\n')
        (self.requestMethod, self.path, self.requestVersion) = requestLine.split()

    def getEnviron(self):
        """
        配置环境变量
        :return dict
        """
        #配置信息从官网拷贝
        #所需的WSGI变量
        environ = {}
        environ['wsgi.input']        = sys.stdin.buffer
        environ['wsgi.errors']       = sys.stderr
        environ['wsgi.version']      = (1, 0)
        environ['wsgi.multithread']  = False
        environ['wsgi.multiprocess'] = True
        environ['wsgi.run_once']     = True
        if environ.get('HTTPS', 'off') in ('on', '1'):
            environ['wsgi.url_scheme'] = 'https'
        else:
            environ['wsgi.url_scheme'] = 'http'
        #所需的CGI变量
        environ['REQUEST_METHOD'] = self.requestMethod
        environ['PATH_INFO'] = self.path
        environ['SERVER_NAME'] = self.serverName
        environ['SERVER_PORT'] = str(self.serverPort)
        return environ

    def setApplication(self, application):
        self.application = application

    def serverRunning(self):

