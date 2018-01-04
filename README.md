# batch_ops
**用途：跨平台(win/linux)批量执行远程命令/传输文件**

#### 主要功能：
- 可批量执行远程命令，上传下载文件
- 完善的命令行提示，比较优雅的输出
- 基于yaml的配置文件，实现灵活的对主机或主机组的操作
- 支持多线程并发执行
- 传输文件实现了类似rsync的机制
- 跨平台，支持Linux和Windows

#### 大致设计和实现思路如下：
- 包依赖docopt(0.6.2)，paramiko(2.4.0)，pyyaml(3.12)
- 将主机组以及主机(格式 name:ip:port)信息写进yaml配置文件，以便灵活选取操作目标
- paramiko 模块实现远程命令和sftp客户端功能。
- 要同时支持并行和串行：抽象出多线程模型，将串行视为多线程中只有一个线程的特例，解决多线程输出乱序问题
- 文件传输功能：由于ssh的sftp子系统只支持单个文件传输，需要处理目录传输时的递归逻辑；尽量减少无谓传输，基于两端文件的mtime和size判断是否需要传输
- 当过程遇到错误时，发送信号给主线程，对于还未开启的线程，则不再开启；对于以开启的线程，等待其完成(这里以任何一种方式将其杀死，都不好阻止其在远程已经开使的命令)

#### 下面先来看一些基本的使用
**帮助信息：**
```
shells]# auto_task --help
Usage:
  auto_task [options] cmd <command> [--parallel] target <targets>...
  auto_task [options] put <src> <dst> [--parallel] target <targets>...
  auto_task [options] get <src> <dst> target <targets>...

Options:
  -h --help             Show this screen.
  -c <config>           YAML file include the remote server's information [default: /root/shells/auto_task.yml]
  -u <user>             Remote username [default: root]
  -p <password>         User's password
  --pkey <private-key>  Local private key [default: ~/.ssh/id_rsa]
  --parallel            Parallel execution, only use with 'cmd' or 'put' [default: False].

  cmd                   Run command on remote server(s),multiple commands sperate by ';'
  put                   Transfer from local to remote. Transport mechanism similar to rsync.
  get                   Transfer from remote to local. Transport mechanism similar to rsync.
  target                Which host(s) or group(s) you want to process,

  Notice:       cmd, get, put can only use one at once.
  For Windows:  Always use double quotes for quote something;
                It's highly recommend that with get or put in Windows, always use '/' instead of '\'
```
**批量执行远程命令:**
```
shells]# auto_task -uroot -uroot cmd "echo 123" target web  ## web is a group contains: web1 and web2

----web1
    ----result:
        123

----web2
    ----result:
        123
```
**上传:**
```
shells]# auto_task -uroot --server name-ip-port.txt put /tmp/ljkapi /tmp/ljkapi target web1 web2

----web1
    ----Uploading /tmp/ljkapi TO /tmp/ljkapi
        /tmp/ljkapi/date.txt
        /tmp/ljkapi/api/demo.tmp

----web2
    ----Uploading /tmp/ljkapi TO /tmp/ljkapi
        /tmp/ljkapi/date.txt
        /tmp/ljkapi/api/demo.tmp
```
**下载**
```
shells]# auto_task -uroot --server name-ip-port.txt get /tmp/ljkapi /tmp/kkk target web1  ## 下载若指定多个目标，只会取第一个

----web1
    ----Downloading /tmp/ljkapi TO /tmp/kkk
        /tmp/ljkapi/date.txt
        /tmp/ljkapi/api/demo.tmp
```

希望能对大家有所帮助。
