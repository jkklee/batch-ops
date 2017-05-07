# auto_task
**用途：远程批量执行命令/传输文件**

这阵子一直在学python，碰巧最近想把线上服务器环境做一些规范化/统一化，于是便萌生了用python写一个小工具的冲动。就功能方面来说，基本上是在“重复造轮子”吧，但是当我用这小工具完成了30多台服务器从系统层面到应用层面的一些规范化工作之后，觉得效果还不算那么low（有点大言不惭~），这才敢拿出来跟小伙伴们分享一下。

(注：笔者所用为python版本为3.5)

#### 经过数次修改，现在主要功能包括：
- 可批量执行远程命令，上传下载文件
- 基于yaml的配置文件，实现灵活的对主机或主机组的操作
- 支持多线程并发执行（对于某些耗时的命令或上传文件，可大大减少等待时间）
- 严格模式（批量执行中若某一台server执行错误则退出）和非严格模式
- 上传下载文件实现了类似rsync的机制
- 完善的命令行提示
- 跨平台，Linux和Windows均可

#### 大致设计和实现思路如下：
- 外部包依赖docopt，paramiko，pyyaml
- 将主机组以及主机(name:ip:port)信息写进yaml配置文件，以便灵活选取操作目标
- 采用了docopt提供命令行界面
- paramiko模块实现远程命令和sftp客户端功能。这里paramiko的sftp实例其只包含了基本的单个文件传输功能；并且不保存文件相关时间信息。
- paramiko 通过sftp实例传输文件环节，这里额外实现“保持文件时间信息”和“实现目录传输”以及“实现类似rsync的传输机制”是要考虑很多问题和逻辑的。传输机制模仿rsync的默认机制，检查文件的mtime和size，有差异才会真正传输。
- 实现了参数中原路径和目标路径的自动判断，例如传输目录时不要求路径后面加‘/’
- 对于远程命令（cmd），可以通过设置（--skip-err）跳过某些server的错误继续执行。例如批量执行‘ls’命令，一般情况会因为某些server上不存在而报错退出
- 全面的错误信息提示。对于执行中的几乎所有可能出现的错误，都有捕获机制获取并输出

#### 下面先来看一些基本的使用
**帮助信息：**
```
shells]# auto_task --help
Usage:
  auto_task [options] cmd <command> [--skip-err] [--parallel] target <targets>...
  auto_task [options] put <src> <dst> [--parallel] target <targets>...
  auto_task [options] get <src> <dst> target <targets>

Options:
  -h --help             Show this screen.
  -c <config>           YAML file include the remote server's information [default: /root/shells/auto_task.yaml]
  -u <user>             Remote username [default: root]
  -p <password>         User's password
  --pkey <private-key>  Local private key [default: /root/.ssh/id_rsa]
  --skip-err            Use with cmd, if skip any server's error and continue process the other servers [default: False].
  --parallel            Parallel execution, only use with cmd or put. This option implies the --skip-err [default: False].

  cmd                   Run command on remote server(s),multiple commands sperate by ';'
  put                   Transfer from local to remote. Transport mechanism similar to rsync.
  get                   Transfer from remote to local. Transport mechanism similar to rsync.
  target                Which host(s) or group(s) you want to process,

  Notice:       cmd, get, put can only use one at once.
  For Windows:  Always use double quotes for quote something;
                It's highly recommend that with get or put in Windows,always use '/' instead of '\'
```
**批量执行远程命令:**
```
shells]# auto_task -uroot -uroot cmd "echo 123" target web  ## web is a group contains: web1 and web2

--------web1
        ----result:
            123

--------web2
        ----result:
            123
```
**上传:**
```
shells]# auto_task -uroot --server name-ip-port.txt put /tmp/ljkapi /tmp/ljkapi target web1 web2

--------web1
    ----Uploading /tmp/ljkapi TO /tmp/ljkapi
        ----Create Remote Dir: /tmp/ljkapi
            /tmp/ljkapi/date.txt
        ----Create Remote Dir: /tmp/ljkapi/api
            /tmp/ljkapi/api/demo.tmp

--------web2
    ----Uploading /tmp/ljkapi TO /tmp/ljkapi
        ----Create Remote Dir: /tmp/ljkapi
            /tmp/ljkapi/date.txt
        ----Create Remote Dir: /tmp/ljkapi/api
            /tmp/ljkapi/api/demo.tmp
```
**下载**
```
shells]# auto_task -uroot --server name-ip-port.txt get /tmp/ljkapi /tmp/kkk target web1  ## 下载应该只指定一个远程主机

--------web1
    ----Downloading /tmp/ljkapi TO /tmp/kkk
        ----Create Local Dir: /tmp/kkk/
            /tmp/ljkapi/date.txt
        ----Create Local Dir: /tmp/kkk/api
            /tmp/ljkapi/api/demo.tmp
```

**另外脚本里包含了两个有用的函数(类)：**

- print_color()函数方便的在Linux下实现打印不同颜色的字体；
- OutputText类在多线程任务需要在中终端打印结果时会非常有用

其实之所以想造这么一个轮子，一方面能锻炼python coding，另一方面当时确实有这么一个需求。而且用自己的工具完成工作也是小有成就的。

另外，在开发过程中对于一些概念性的东西也都有了更深入的了解：

- 例如在使用paramiko模块的过程中，又促使我深入的了解了一些ssh登陆的详细过程。
- 又如用到了线程模型，更深入的了解了线程进程相关的概念。

所以作为一枚运维老司机，越来越深刻的理解到“运维”和“开发”这俩概念之间的相互促进。希望大家共勉
