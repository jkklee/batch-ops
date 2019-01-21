#!/usr/bin/env python3
# coding:utf-8
"""
Usage:
  auto_task [options] cmd <command> [--parallel][--skip-err] target <targets>...
  auto_task [options] put <src> <dst> [--parallel] target <targets>...
  auto_task [options] get <src> <dst> target <targets>...


Options:
  -h --help             Show this screen
  -c <config>           YAML file include the remote server's information [default: /root/shells/auto_task.yml]
  -u <user>             Remote username [default: root]
  -p <password>         User's password
  --pkey <private-key>  Local private key [default: ~/.ssh/id_rsa]
  --parallel            Parallel execution, only use with 'cmd' or 'put' [default: False]
  --skip-err            When remote command encounter errors on some server(s), continue run on remainder [default: False]

  cmd                   Run command on remote server(s),multiple commands sperate by ';'
  put                   Transfer from local to remote. Transport mechanism similar to rsync
  get                   Transfer from remote to local. Transport mechanism similar to rsync
  target                Which host(s) or group(s) you want to process

  Notice:       cmd, get, put can only use one at once.
  For Windows:  Always use double quotes for quote something;
                It's highly recommend that with get or put in Windows, always use '/' instead of '\\'
"""

"""
by ljk 20160704
update at 20171231
"""
import os
import yaml
import stat
import threading
from docopt import docopt
from platform import uname
from sys import exit, stdout
from paramiko import SSHClient, AutoAddPolicy

"""
因为涉及了(多)线程,所以将串行也归为单线程,这样可以统一用线程的思路,而不必编写一套多线程模型一套串行模型。
也因为多线程,所以输出用print()的话,各server的输出会对不上号,所以引入了OutputText类,将每个server的输出统一保存起来,最后打印出来
但是这样依然无法避免多个线程同时完成了,同时打印各自的最终结果。也就是说多线程任务最终需要输出时,输出这个动作必须要串行
"""
global_lock = threading.Lock()
computer = uname().system
event = threading.Event()
INDENT_1 = 0
INDENT_2 = 4
INDENT_3 = 8


class OutputText:
    """该类具有write()方法,用来存储每台server的执行结果.
    因为引入了多线程异步执行才需要这么做,以保证异步执行多台server的输出不会乱.
    为了简洁,并行与串行的输出都用这一套东西"""
    def __init__(self):
        self.buffer = []

    def write_or_print(self, *args, color=None):
        """并行模式先缓存最后加锁输出; 串行模式直接输出"""
        # print(args)  # debug 可观察到并行时内部各输出的产生顺序
        if arguments['--parallel']:
            if color and not computer == 'Windows':
                self.buffer.append('\033[0;{}m'.format(color))
                self.buffer.extend(args)
                self.buffer.append('\033[0m')
            else:
                self.buffer.extend(args)
        else:
            if color and not computer == 'Windows':
                for string in args:
                    self.print_color(string, color=color, end='')
            else:
                for string in args:
                    print(string, end='')

    def print_lock(self):
        """并发模式下,所有的输出动作都要加锁"""
        if self.buffer:
            with global_lock:
                for line in self.buffer:
                    print(line, end='')

    @staticmethod
    def print_color(text, color=31, sep=' ', end='\n', file=stdout, flush=False):
        """打印彩色字体,color默认为红色
        该方法只针对Linux有效"""
        if computer == 'Windows':
            print(text, sep=sep, end=end, file=file, flush=flush)
        else:
            print('\033[0;{}m'.format(color), end='')
            print(text, sep=sep, end=end, file=file, flush=flush)
            print('\033[0m', end='')


class AutoTask:
    def __init__(self, hostname, ip, port):
        self.hostname = hostname
        self.ip = ip
        self.port = int(port)
        self.client = SSHClient()
        self.client.set_missing_host_key_policy(AutoAddPolicy())
        self.output = OutputText()
        self.sftp = None
        self.output.write_or_print('\n----{}\n'.format(hostname))

    def create_sshclient(self):
        """根据命令行提供的参数,建立到远程server的ssh链接.这段本应在run_command()函数内部。
        摘出来的目的是为了让sftp功能也通过sshclient对象来创建sftp对象,因为初步观察t.connect()方法在使用key时有问题"""
        try:
            # client.connect()方法会调用Transport类额外创建一个daemon线程
            self.client.connect(self.ip, port=self.port, username=arguments['-u'], password=arguments['-p'], key_filename=arguments['--pkey'])
            return True
        except Exception as err:  # 有异常,打印异常,并返回'error'
            self.output.write_or_print('{}{} SSH connect error: {}\n'.format(' ' * INDENT_2, self.hostname, err), color=31)
            self.output.print_lock()
            return False

    def run_command(self, cmd):
        """
        执行远程命令的主函数
        client: paramiko.client.SSHClient object
        cmd: 待执行的命令
        """
        # stdout 假如通过分号提供单行的多条命令,所有命令的输出（在linux终端会输出的内容）都会存储于stdout
        # 据观察,下面三个变量的特点是无论"如何引用过一次"之后,其内容就会清空
        # 有readlines()的地方都是流,用过之后就没有了
        with self.client:
            _, stdout_, stderr_ = self.client.exec_command(cmd)
            copy_out, copy_err = stdout_.readlines(), stderr_.readlines()
            copy_out_ = ('%s%s' % (' ' * INDENT_3, i) for i in copy_out)
            copy_err_ = ('%s%s' % (' ' * INDENT_3, i) for i in copy_err)
            del stdout_, stderr_
            if copy_out and copy_err:
                self.output.write_or_print('%s----result:\n' % (' ' * INDENT_2))
                self.output.write_or_print(*copy_out_)
                self.output.write_or_print(*copy_err_, color=31)
                self.output.print_lock()
            elif copy_out:
                self.output.write_or_print('%s----result:\n' % (' ' * INDENT_2))
                self.output.write_or_print(*copy_out_)
                self.output.print_lock()
            elif copy_err:
                self.output.write_or_print('%s----error:\n' % (' ' * INDENT_2), color=31)
                self.output.write_or_print(*copy_err_, color=31)
                self.output.print_lock()
                if not arguments['--skip-err']:
                    event.set()
            else:  # 既无stdout也无stderr,例如nginx -s reload
                self.output.write_or_print('%s----result:\n' % (' ' * INDENT_2))
                self.output.print_lock()

    # 先定义sftp_transfer()函数所需的一些子函数
    @staticmethod
    def _process_arg_dir(target):
        """处理目录时,检查用户输入,在路径后面加上/ (win 平台下python, /和\\都可作为分隔符)"""
        if not target.endswith('/'):
            return target + '/'
        else:
            return target

    def _sftp_put(self, src, dst, if_raise=False):
        """封装put,增加相应输出,并依据m_time和size判断两端文件一致性,决定是否传输该文件"""
        src_stat = self._path_stat(src, 'local')
        dst_stat = self._path_stat(dst, 'remote')    # 一次远非核心程调用
        if isinstance(dst_stat, str) or not (int(src_stat.st_mtime) == dst_stat.st_mtime and src_stat.st_size == dst_stat.st_size):
            try:
                self.sftp.put(src, dst)
                self.sftp.utime(dst, (src_stat.st_atime, src_stat.st_mtime))    # 一次远非核心程调用
                self.sftp.chmod(dst, src_stat.st_mode)  # 一次远非核心程调用
                self.output.write_or_print('%s%s\n' % (' ' * INDENT_3, src))
            except Exception as e:
                if not if_raise:
                    self.output.write_or_print('{}sftp.put({}, {}): {}\n'.format(' '*INDENT_3, src, dst, e), color=31)
                    self.output.print_lock()
                    event.set()
                    exit()
                else:
                    raise

    def _sftp_get(self, src, dst, if_raise=False):
        """封装get,增加相应输出,并依据m_time和size判断两端文件一致性,决定是否传输该文件"""
        src_stat = self._path_stat(src, 'remote')    # 一次远非核心程调用
        dst_stat = self._path_stat(dst, 'local')
        if isinstance(dst_stat, str) or not (src_stat.st_mtime == int(dst_stat.st_mtime) and src_stat.st_size == dst_stat.st_size):
            try:
                self.sftp.get(src, dst)
                os.utime(dst, (src_stat.st_atime, src_stat.st_mtime))
                os.chmod(dst, src_stat.st_mode)
                self.output.write_or_print('%s%s\n' % (' ' * INDENT_3, src))
            except Exception as err:
                if not if_raise:
                    self.output.write_or_print('{}sftp.get({}, {}): {}\n'.format(' '*INDENT_3, src, dst, err), color=31)
                    self.output.print_lock()
                    event.set()
                    exit()
                else:
                    raise

    def _path_stat(self, path_, side):
        """获取指定路径的 stat"""
        try:
            if side == 'remote':
                return self.sftp.stat(path_)
            if side == 'local':
                return os.stat(path_)
        except FileNotFoundError:
            return 'no_exist'
        except Exception:
            raise    # 这里暂时不清楚其他的异常类型,所以先raise

    def _check_path_type(self, path_, side):
        """通过client对象在远程linux执行命令,来判断远程路径是否存在,是文件还是目录"""
        if side == 'local':
            if os.path.isfile(path_):
                return 'file'
            elif os.path.isdir(path_):
                return 'directory'
            else:
                return 'no_exist'
        if side == 'remote':
            try:
                path_attr = self.sftp.stat(path_)
                if stat.S_ISREG(path_attr.st_mode):
                    return 'file'
                if stat.S_ISDIR(path_attr.st_mode):
                    return 'directory'
            except FileNotFoundError:
                return 'no_exist'
            except Exception:
                raise

    def _makedirs_local(self, dirname, r_path):
        """在本地递归创建目录. 基本参照os.makedirs(), 增加了对时间和权限的同步功能"""
        if os.path.isdir(dirname):
            return
        l_head, l_tail = os.path.split(dirname)
        r_head, r_tail = os.path.split(r_path)
        if not l_tail:
            l_head, l_tail = os.path.split(l_head)
        if not r_tail:
            r_head, r_tail = os.path.split(r_head)

        if l_head and l_tail and not os.path.exists(l_head):
            try:
                self._makedirs_local(l_head, r_head)
            except FileExistsError:
                # Defeats race condition when another thread created the path
                pass
        try:
            os.mkdir(dirname)
            remote_stat = self._path_stat(r_path, 'remote')    # 一次远非核心程调用
            os.utime(dirname, (remote_stat.st_atime, remote_stat.st_mtime))
            os.chmod(dirname, remote_stat.st_mode)
        except Exception as e:
            self.output.write_or_print('{}Error: os.mkdir({}): {}\n'.format(' '*INDENT_3, dirname, e), color=31)
            self.output.print_lock()
            event.set()
            exit()

    def _makedirs_remote(self, dirname, l_path):
        if self._check_path_type(dirname, 'remote') == 'directory':    # 一次远非核心程调用
            return
        l_head, l_tail = os.path.split(l_path)
        r_head, r_tail = os.path.split(dirname)
        if not l_tail:
            l_head, l_tail = os.path.split(l_head)
        if not r_tail:
            r_head, r_tail = os.path.split(r_head)

        if r_head and r_tail and self._check_path_type(r_head, 'remote') == 'no_exist':    # 一次远非核心程调用
            try:
                self._makedirs_remote(r_head, l_head)
            except FileExistsError:
                pass
        try:
            self.sftp.mkdir(dirname)
            local_stat = self._path_stat(l_path, 'local')
            self.sftp.utime(dirname, (local_stat.st_atime, local_stat.st_mtime))    # 一次远非核心程调用
            self.sftp.chmod(dirname, local_stat.st_mode)    # 一次远非核心程调用
        except Exception as e:
            self.output.write_or_print('{}Error: sftp.mkdir({}): {}\n'.format(' '*INDENT_3, dirname, e), color=31)
            self.output.print_lock()
            event.set()
            exit()

    def _put_dirs(self, src_dir, dst_dir):
        """put目录时: 通过一次os.walk(), 先循环将所有的源端目录和目标端目录的结构同步好; 再循环上传所有文件"""
        for root, dirs, files in os.walk(src_dir):
            for dir_ in dirs:
                s_dir = os.path.join(root, dir_).replace('\\', '/')
                d_dir = s_dir.replace(src_dir, dst_dir, 1)
                self._makedirs_remote(d_dir, s_dir)
            for file_ in files:
                s_file = os.path.join(root, file_).replace('\\', '/')  # 逐级取得每个源端文件的全路径
                d_file = s_file.replace(src_dir, dst_dir, 1)  # 取得每个目标端文件的全路径
                self._sftp_put(s_file, d_file)

    def _get_dirs(self, src_dir, ori_src, ori_dst):
        """
        get目录时: 通过sftp.listdir()处理远端的目录,并在client端创建不存在的目录,然后文件执行get操作,目录则递归处理.
        ori_src: 从命令行获取的 源路径
        ori_dst: 从命令行获取的 目标路径
        src_dir: 当前处理到的源端目录, 第一次的引用值与ori_src相同
        """
        dst_dir = src_dir.replace(ori_src, ori_dst, 1)
        if not os.path.exists(dst_dir):
            self._makedirs_local(dst_dir, src_dir)
        for name in self.sftp.listdir(src_dir):    # 一次远非核心程调用
            s_path = os.path.join(src_dir, name).replace('\\', '/')    # 在win平台下运行的话需要将'\\'替换为'/'，否则s_path在远端不存在
            d_path = s_path.replace(ori_src, ori_dst, 1)
            s_path_type = self._check_path_type(s_path, 'remote')    # 一次远非核心程调用
            if s_path_type == 'file':
                self._sftp_get(s_path, d_path)
            if s_path_type == 'directory':
                self._get_dirs(s_path, ori_src, ori_dst)
    # -----子函数定义完毕-----

    def sftp_transfer(self, source_path, destination_path, method):
        """
        文件传输的 主函数
        paramiko的sftp client传输,只能单个文件作为参数,并且不会保留文件的时间信息,这两点都需要代码里额外处理
        source: 原文件(为文件时); 原目录(为目录时,并且作为递归处理时的目录前缀)
        destination: 目标文件(为文件时); 目标目录(为目录时, 并且作为递归处理时的目录前缀)
        client: paramiko.client.SSHClient object
        output:存储输出的对象
        """
        with self.client:
            try:
                self.sftp = self.client.open_sftp()
            except Exception as err:
                self.output.write_or_print('%sopen_sftp error: %s\n' % (' '*INDENT_3, str(err)), color=31)
                self.output.print_lock()
                event.set()
                exit()
            if computer == 'Windows':
                '''根据put或get,将windows路径中的 \ 分隔符替换为 / '''
                if arguments["put"]:
                    source_path = source_path.replace('\\', '/')
                elif arguments["get"]:
                    destination_path = destination_path.replace('\\', '/')

            # -----上传逻辑-----
            if method == 'put':
                '''异常情况: 
                `sftp.put(file, dir)`, sftp.put(file, file/)`, 
                `sftp.put(file, dir/)` dir is ok, but has a subdir that has a same name with file
                以上三种会 raise `OSError: Failure`
                `sftp.put(dir, file)`, `sftp.put(dir, file/dir)` raise `IsADirectoryError: [Errno 21] Is a directory: scr_dir`
                 '''
                self.output.write_or_print('%s----Uploading %s TO %s\n' % (' '*INDENT_2, source_path, destination_path))
                source_type = self._check_path_type(source_path, 'local')
                if source_type == 'file':
                    '''判断source_path是文件'''
                    if destination_path.endswith('/'):
                        destination_path = os.path.join(destination_path, os.path.basename(source_path)).replace('\\', '/')
                    dst_parent_type = self._check_path_type(os.path.dirname(destination_path), 'remote')    # 一次远非核心程调用
                    if dst_parent_type == 'file':
                        '''专门应对 file ----> file/ 这种情况,因为这种情况sftp对象会抛出 OSError(而非os模块抛出 FileExistsError),捕捉杀伤面太大'''
                        self.output.write_or_print("{}Error: remote {} is file\n".format(' '*INDENT_3, os.path.dirname(destination_path)), color=31)
                        self.output.print_lock()
                        event.set()
                        exit()
                    if dst_parent_type == 'no_exist':
                        self._makedirs_remote(os.path.dirname(destination_path), os.path.dirname(source_path))
                    self._sftp_put(source_path, destination_path)
                    self.output.print_lock()
                elif source_type == 'directory':
                    '''判断src是目录'''
                    source_path, destination_path = self._process_arg_dir(source_path), self._process_arg_dir(destination_path)
                    self._put_dirs(source_path, destination_path)
                    self.output.print_lock()
                else:
                    self.output.write_or_print('%sLocal %s is not exist\n' % (' '*INDENT_3, source_path), color=31)
                    self.output.print_lock()
                    event.set()
                    exit()

            # -----下载逻辑-----
            if method == 'get':
                '''异常情况: `get(file, dir)`, `get(dir, file/)` raise `IsADirectoryError: [Errno 21] Is a directory: dst_dir`
                `get(dir, file)` raise `OSError: Failure`
                '''
                self.output.write_or_print('%s----Downloading %s TO %s\n' % (' '*INDENT_2, source_path, destination_path))
                source_type = self._check_path_type(source_path, 'remote')    # 一次远非核心程调用
                # destination_type = self._check_path_type(destination_path, 'local')
                if source_type == 'file':
                    '''判断source_path是文件'''
                    if destination_path.endswith('/') or destination_path.endswith('\\'):
                        destination_path = os.path.join(destination_path, os.path.basename(source_path)).replace('\\', '/')
                    dst_parent_type = self._check_path_type(os.path.dirname(destination_path), 'local')
                    if dst_parent_type == 'file':
                        self.output.write_or_print("{}Error: local {} is file\n".format(' '*INDENT_3, os.path.dirname(destination_path)), color=31)
                        self.output.print_lock()
                        event.set()
                        exit()
                    if dst_parent_type == 'no_exist':
                        self._makedirs_local(os.path.dirname(destination_path), os.path.dirname(source_path))
                    self._sftp_get(source_path, destination_path)
                    self.output.print_lock()
                elif source_type == 'directory':
                    '''判断source_path是目录'''
                    source_path, destination_path = self._process_arg_dir(source_path), self._process_arg_dir(destination_path)
                    self._get_dirs(source_path, source_path, destination_path)
                    self.output.print_lock()
                else:
                    self.output.write_or_print('%sRemote %s is not exist\n' % (' '*INDENT_3, source_path), color=31)
                    self.output.print_lock()
                    event.set()
                    exit()


def get_keys(keys, dic=None, ret=None):
    """
    从长度和结构未知的字典对象中取出指定key的值(若key的值为字典，则递归展示其最小粒度的键值对)
    keys: 可迭代容器,元素为要获取值的键
    dic: 字典对象
    ret: 一个外部的空集合, 用来存储得到的 k v 信息
    """
    for key in keys:
        if key in dic:
            if isinstance(dic[key], dict):
                get_keys(dic[key].keys(), dic=dic[key], ret=ret)
            else:
                ret.add((key, dic[key]))
        else:
            for inner in dic:
                if isinstance(dic[inner], dict):
                    get_keys([key], dic=dic[inner], ret=ret)                    

                    
def get_host_info(targets):
    """从配置文件中,取得要处理的host(s)/group(s)的主机名,主机ip,端口
    targets: 待处理目标(list类型),值为 all(代表所有) 或 host(s)/group(s)"""
    try:
        with open(arguments['-c']) as conf_content:
            conf = yaml.load(conf_content)
    except Exception as e:
        OutputText.print_color("Can't parse config file: {}".format(e), color=31)
        exit(10)
    if arguments['get']:
        targets = [targets[0]]
    info = set()
    get_keys(targets, dic=conf, ret=info)
    return info


def main():
    global arguments
    arguments = docopt(__doc__)
    if arguments['--pkey'] == '~/.ssh/id_rsa':
        arguments['--pkey'] = os.path.join(os.path.expanduser('~'), '.ssh/id_rsa')
    for hostname, ip_port in get_host_info(arguments['<targets>']):
        '''循环处理每个主机'''
        ip, port = ip_port.split(':')
        if event.is_set():
            break
        auto_task = AutoTask(hostname, ip, port)
        if not auto_task.create_sshclient():
            break
        # 区别处理 cmd put get参数
        if arguments['cmd']:
            t = threading.Thread(target=auto_task.run_command, args=(arguments['<command>'],))
        elif arguments['put']:
            t = threading.Thread(target=auto_task.sftp_transfer, args=(arguments['<src>'], arguments['<dst>'], 'put'))
        elif arguments['get']:
            t = threading.Thread(target=auto_task.sftp_transfer, args=(arguments['<src>'], arguments['<dst>'], 'get'))
        t.start()
        if not arguments['--parallel']:
            t.join()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        '''注意:Ctrl+C会在这里企图退出主线程,因为触发Ctrl+C之前可能已经开启了(不确定数量的)子线程(即已经开始执行远程命令),
        故而主线程会等待其子线程退出(并打印结果)后再退出.这种行为是正确的,因为一旦开始执行远程命令,即使关闭了其ssh连接,
        远程server上已开启的命令也不会因此中断,故而应该等待其完成并打印结果.
        '''
        if threading.active_count() > 1:
            OutputText.print_color('\n----bye----: waiting for sub_threads exit ...')
        else:
            OutputText.print_color('\n----bye----')

