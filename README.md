# batch_ops
**跨平台(win/linux)批量运维小工具：执行远程命令/上传下载文件**

### 特点：
- 完善的命令行提示，比较优雅的输出
- 基于yaml的配置文件，实现灵活的对主机或主机组的操作
- 支持多线程并发执行
- 批量执行支持忽略某个（些）节点的错误
- 传输文件实现了类似rsync的机制
- 跨平台，支持Linux和Windows

### 依赖和实现思路：
- 包依赖：docopt(0.6.2)，paramiko(2.4.0)，pyyaml(3.12)
- 将主机组以及主机(格式 name:ip:port)信息写进yaml配置文件，以便灵活选取操作目标
- paramiko 模块实现远程命令和sftp客户端功能。
- 要同时支持并行和串行：抽象出多线程模型，将串行视为多线程中只有一个线程的特例，解决多线程输出乱序问题
- 文件传输功能：由于ssh的sftp子系统只支持单个文件传输，所以需要以递归思想传输目录；尽量减少无谓通信；基于两端文件的mtime和size判断是否需要传输
- 当过程遇到错误时，发送信号给主线程，对于还未开启的线程，则不再开启；对于以开启的线程，等待其完成（这里以任何一种方式将其杀死，都不好阻止其在远程已经开使的命令）

### 使用说明
#### 帮助信息：
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
#### 批量执行远程命令:
以**主机组**为单位批量执行远程命令
```
# web is a group, contains: web1 and web2
shells]# auto_task -uroot cmd "echo 123" target web

----web1
    ----result:
        123

----web2
    ----result:
        123
```
上例也可以**主机**为单位批量执行
```
shells]# auto_task -uroot cmd "echo 123" target web1 web2
```
也可以通过`--parallel`参数实现并发执行
```
shells]# auto_task -uroot cmd "yum -y install rsync" target web1 web2 --parallel
----web1
    ----result:
        Loaded plugins: fastestmirror
        Loading mirror speeds from cached hostfile
         * base: mirrors.tuna.tsinghua.edu.cn
         * extras: mirrors.tuna.tsinghua.edu.cn
         * updates: mirrors.tuna.tsinghua.edu.cn
        Setting up Install Process
        Package rsync-3.0.6-12.el6.x86_64 already installed and latest version
        Nothing to do

----web2
    ----result:
        Loaded plugins: fastestmirror
        Loading mirror speeds from cached hostfile
         * base: mirrors.tuna.tsinghua.edu.cn
         * extras: mirrors.tuna.tsinghua.edu.cn
         * updates: mirrors.tuna.tsinghua.edu.cn
        Setting up Install Process
        Package rsync-3.0.6-12.el6.x86_64 already installed and latest version
        Nothing to do
```
也可通过`--skip-err`参数忽略批量执行中的错误
```
shells]# auto_task -u root cmd "ls -l /nginx_log" target web2 web3 --skip-err     

----web2
    ----error:
        ls: 无法访问/nginx_log: 没有那个文件或目录

----web3
    ----result:
        总用量 0
        -rw-r--r-- 1 root root 0 4月  19 14:21 api.access
        -rw-r--r-- 1 root root 0 4月  19 14:20 www.access
```
**关于--skip-err：**
不提供此参数时  
串行情况下：遇到错误便退出，不会继续在后续的主机上执行命令  
并行情况下：对于还未开启的线程（一个线程对应一个主机），则不再开启；对于以开启的线程，等待其完成（或报错）

#### 上传：
```
shells]# auto_task -uroot -c name-ip-port.txt put /tmp/ljkapi /tmp/ljkapi target web1 web2

----web1
    ----Uploading /tmp/ljkapi TO /tmp/ljkapi
        /tmp/ljkapi/date.txt
        /tmp/ljkapi/api/demo.tmp

----web2
    ----Uploading /tmp/ljkapi TO /tmp/ljkapi
        /tmp/ljkapi/date.txt
        /tmp/ljkapi/api/demo.tmp
```
#### 下载：
```
shells]# auto_task -uroot -c name-ip-port.txt get /tmp/ljkapi /tmp/kkk target web1  ## 下载若指定多个目标，只会取第一个

----web1
    ----Downloading /tmp/ljkapi TO /tmp/kkk
        /tmp/ljkapi/date.txt
        /tmp/ljkapi/api/demo.tmp
```

希望能对大家有所帮助。
