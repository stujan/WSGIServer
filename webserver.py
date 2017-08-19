###webserver---采用wsgi协议
import socket
import sys
import datetime
import errno
import signal
import os

class WSGIServer(object):
    REQUESR_SIZE = 1024

    def __init__(self, serverAddress):
        # self.serverName = None
        # self.serverPort = None
        #self.responseHeader = None
        self.application = None
        #创建一个socket链接
        self.listenSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        #允许使用相同的地址
        self.listenSock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        #绑定ip + port
        self.listenSock.bind(serverAddress)
        #最多处理多少请求数目
        self.listenSock.listen(self.REQUESR_SIZE)
        #得到hostname和端口
        host, self.serverPort = self.listenSock.getsockname()[:2]
        self.serverName = socket.getfqdn(host)


    def finishResponse(self, result, connection, responseHeader):
        """
        对发起的请求进行响应
        函数只是对返回的内容进行格式化处理
        :param result:返回的结果信息
        :return:
        """
        try:
            status, headers = responseHeader
            response = 'HTTP/1.1 {status}\r\n'.format(status=status)
            for header in headers:
                response += '{0}: {1}\r\n'.format(*header)
            response += '\r\n'
            for data in result:
                response += data.decode()
            print(''.join(
                '> {line}\n'.format(line=line) for line in response.splitlines()
            ))
            connection.sendall(response.encode())
        finally:
            connection.close()

    def handleRequest(self, connection):
        """
        当接受到请求时，调用
        :param connection: 客户端链接
        :return:
        """
        responseHeader = None
        def startResponse(status, header, exc_info=None):
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
            nonlocal responseHeader
            # 设置基本的服务器头部信息
            serverHeader = [
                ('Date', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                ('Server', "SanJay's WSGIServer v1.0")
            ]
            # 设置响应码，并把两种头部信息相加
            responseHeader = [status, header + serverHeader]

        #客户端发起的请求
        requestData = connection.recv(1024).decode()
        #分解请求信息，将信息提取出来
        requestMethod, path, requestVersion = self.parseRequest(requestData)
        #配置环境信息
        env = self.getEnviron(requestMethod, path, requestVersion)
        #配置完成信息之后，需要向后台的web程序发起处理请求了
        result = self.application(env, startResponse)
        #请求，获取返回信息后，可以反馈给客户端啦
        self.finishResponse(result, connection, responseHeader)

    def parseRequest(self, requestData):
        """
        对requestData进行分解
        从而设置请求方式 method  -- get/post,,,,
        请求路径path  --  对应的文件路径，很必要
        请求的版本   --- http 1.1
        """
        requestLine = requestData.splitlines()[0]
        requestLine = requestLine.rstrip('\r\n')
        (requestMethod, path, requestVersion) = requestLine.split()
        return requestMethod, path, requestVersion

    def getEnviron(self, requestMethod, path, requestVersion):
        """
        配置环境变量
        :return dict
        """
        #配置信息从官网拷贝
        #所需的WSGI变量
        environ = {}
        environ['wsgi.input']        = sys.stdin.buffer
        environ['wsgi.errors']       = sys.stderr
        environ['wsgi.version']      = (1,0)
        environ['wsgi.multithread']  = False
        environ['wsgi.multiprocess'] = True
        environ['wsgi.run_once']     = True
        if environ.get('HTTPS', 'off') in ('on', '1'):
            environ['wsgi.url_scheme'] = 'https'
        else:
            environ['wsgi.url_scheme'] = 'http'
        #所需的CGI变量
        environ['REQUEST_METHOD'] = requestMethod
        environ['PATH_INFO'] = path
        environ['SERVER_NAME'] = self.serverName
        environ['SERVER_PORT'] = str(self.serverPort)
        return environ

    def setApplication(self, application):
        self.application = application

    def dealSignal(self, signum, frame):
        """
        当fork出来的子进程结束后，（内核）会向父进程返回一个sigchld信号，
        内核会释放进程占用的所有资源：占用的内存、打开的文件等，但是仍保留一些信息：进程ID、退出状态、运行时间，
        父进程调用wait/waitpid可将进程表清空，在父进程取走之前，子进程称为zombie。
        当同时出现大量sigchld信号时，因为他们是不排队的，可能会出现丢失部分信号，因此没有wait()
        造成zombie
        发送过来的信号数目可能少于真实的子进程数目！！！
        解决方法是用循环的写法，
        逻辑如下：
        当接受发送过来的信号时，执行该函数（可能同时有多个信号同时到达，因此可能出现多次执行。。可能影响性能？）
        避免丢失情况的发生
        等待所有子进程结束os.waitpid(-1)
        如果返回pid不为0,表示还有子进程没wait(),继续执行循环
        如果pid为0,则return
        :param signum:
        :param frame:
        :return:
        """
        while True:
            try:
                #等待进程id为pid的进程结束，返回一个tuple，包括进程的进程ID和退出信息
                #当参数为-1时表示等待任何子进程
                #如果pid小于-1，则获取进程组id为pid的绝对值的任何一个进程
                #当系统调用返回-1时，抛出一个OSError异常
                pid, status = os.waitpid(
                    -1, #等待所有的子进程结束
                    os.WNOHANG #表示没有使父进程挂起，不采用阻塞方式（怕卡死），采用非阻塞，立即返回，
                )
            except OSError:
                return
            if pid == 0: #没有zombie,没有错过任何sigchld信号,就返回
                return

    def serverRunning(self):
        listenSock = self.listenSock
        signal.signal(signal.SIGCHLD, self.dealSignal)
        while True:
            try:
                #接受到一个客户端请求
                client, address = listenSock.accept()
            except IOError as e:
                code, msg = e.args
                #内存不满的情况下，直接continue掉
                if code == errno.EINTR:
                    continue
                else:
                    raise
            #通过fork子进程处理
            #fork之后，会有一个父进程的拷贝样本--子进程
            #但是不同的是，返回值pid是不同的，可通过pid判断
            pid = os.fork()
            if pid < 0:
                sys.stdout.write("fork error")
            #为0时，表示为子进程

            elif pid == 0:
                #服务端socket一个即可,把拷贝的close()
                listenSock.close()
                self.handleRequest(client)
                #执行完毕后，关闭双方的链接
                client.close()
                #退出子进程----此时内核会返回sigchld信号
                os._exit(0)
            #不为0时为父进程
            else:
                #为什么父进程关闭双方socket链接后，还可以继续通信
                #因为判断关闭socket连接是采用描述符的，0的时候关闭
                #fork之后，描述符为2，父进关闭后为1,不关闭
                client.close()
                #回收子进程，不推荐，这样是阻塞主进程的，会导致只能接受一个客户端连接
                # while True:
                #     wpid, status = os.waitpid(pid,0)
                #     if os.WIFEXITED(status) or os.WIFSIGNALED(status):
                #         break

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('Provide a WSGI application object as module:callable')
    appPath = sys.argv[1]
    module, application = appPath.split(':')
    module = __import__(module)
    application = getattr(module, application)
    server = WSGIServer(('localhost', 8080))
    server.setApplication(application)
    print('WSGIServer: Serving HTTP on port {port} ...\n'.format(port=8080))
    server.serverRunning()
