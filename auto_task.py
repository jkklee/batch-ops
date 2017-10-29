#!/bin/env python
# coding:utf-8
"""
Usage:
  auto_task [options] cmd <command> [--skip-err] [--parallel] target <targets>...
  auto_task [options] put <src> <dst> [--parallel] target <targets>...
  auto_task [options] get <src> <dst> target <targets>...


Options:
  -h --help             Show this screen.
  -c <config>           YAML file include the remote server's information [default: /root/shells/auto_task.yml]
  -u <user>             Remote username [default: root]
  -p <password>         User's password
  --pkey <private-key>  Local private key [default: /root/.ssh/id_rsa]
  --skip-err            Use with cmd, if sikp any server's error and continue process the other servers [default: False].
  --parallel            Parallel execution, only use with cmd or put. This option implies the --skip-err [default: False].

  cmd                   Run command on remote server(s),multiple commands sperate by ';'
  put                   Transfer from local to remote. Transport mechanism similar to rsync.
  get                   Transfer from remote to local. Transport mechanism similar to rsync.
  target                Which host(s) or group(s) you want to process,

  Notice:       cmd, get, put can only use one at once.
  For Windows:  Always use double quotes for quote something;
                It's highly recommend that with get or put in Windows,always use '/' instead of '\\'
"""

"""
by ljk 20160704
update at 20170111
"""
from docopt import docopt
import yaml
from paramiko import SSHClient, AutoAddPolicy
from os import path, walk, makedirs, stat, utime
from re import search
from sys import exit, stdout
import platform
from math import floor
import threading

"""
因为涉及了(多)线程,所以我们将串行也归为单线程,这样可以统一用线程的一些思路,而不必编写一套多线程模型一套串行模型。
也因为多线程,所以输出用print()的话,各server的输出会对不上号,所以引入了OutputText类,将每个server的输出统一保存起来,最后打印出来
但是这样依然无法避免多个线程同时完成了,同时打印各自的最终结果。也就是说多线程任务最终需要输出时,输出这个动作必须要串行
"""


class OutputText:
    """该类的对象具有write()方法,用来存储每台server的执行结果.
    因为引入了多线程异步执行才需要这么做,以保证异步执行多台server的输出不会乱.
    为了简洁,并行与串行的输出就都用这一套东西了"""
    def __init__(self):
        self.buffer = []

    def write(self, *args, color=None):
        if color:
            if platform.uname().system == 'Windows':
                self.buffer.extend(args)
            else:
                self.buffer.extend('\033[0;{}m'.format(color))
                self.buffer.extend(args)
                self.buffer.extend('\033[0m')
        else:
            self.buffer.extend(args)

    def print_lock(self):
        global global_lock
        """并发模式下,所有的输出动作都要加锁"""
        global_lock.acquire()
        for line in self.buffer:
            print(line, end='')
        global_lock.release()


def print_color(text, color=31, sep=' ', end='\n', file=stdout, flush=False):
    """打印彩色字体,color默认为红色
    该方法只针对Linux有效"""
    if platform.uname().system == 'Windows':
        print(text, sep=sep, end=end, file=file, flush=flush)
    else:
        print('\033[0;{}m'.format(color), end='')
        print(text, sep=sep, end=end, file=file, flush=flush)
        print('\033[0m', end='')


def get_ip_port(conf_dict,target):
    """从配置文件中,取得要处理的host(s)/group(s)的主机名,主机ip,端口
    conf_dict: 对yaml配置文件的解析结果
    target: (list类型)待处理目标,值为 all 或 host(s)/group(s)"""
    if len(target) == 1 and target[0] == 'all':
        for v in conf_dict.values():
            for single_server in v:
                yield(single_server.split(':'))
    else:
        break_flag = False  # 用来支持多层for循环的正确break
        for a in target:
            if a in conf_dict.keys():
                for single_server in conf_dict[a]:
                    yield(single_server.split(':'))
            else:
                for v in conf_dict.values():
                    if v:
                        for single_server in v:
                            if a in single_server:
                                yield(single_server.split(':'))
                                break_flag = True
                                break
                            else:
                                break_flag = False
                                continue
                    if break_flag:
                        break


def create_sshclient(server_ip, port, output):
    """根据命令行提供的参数,建立到远程server的ssh链接.这段本应在run_command()函数内部。
    摘出来的目的是为了让sftp功能也通过sshclient对象来创建sftp对象,因为初步观察t.connect()方法在使用key时有问题
    output:存储输出的对象"""
    local_client = threading.local()  # 多线程中每个线程要在函数内某些保持自己特定值
    local_client.client = SSHClient()
    local_client.client.set_missing_host_key_policy(AutoAddPolicy())
    try:
        # client.connect()方法额外单独外创建一个线程
        local_client.client.connect(server_ip, port=int(port), username=arguments['-u'], password=arguments['-p'], key_filename=arguments['--pkey'])
    except Exception as err:  # 有异常,打印异常,并返回'error'
        output.write('{}----{} ssh connect error: {}\n'.format(' ' * 4, server_ip, err), color=31)
        return 'error'
    else:
        return local_client.client  # 返回的client对象在每个线程内是不同的


# ----------
# run_command()执行远程命令
# ----------
def run_command(client, output):
    """
    执行远程命令的主函数
    client: paramiko.client.SSHClient object
    output: 存储输出的对象
    """
    # stdout 假如通过分号提供单行的多条命令,所有命令的输出（在linux终端会输出的内容）都会存储于stdout
    # 据观察,下面三个变量的特点是无论"如何引用过一次"之后,其内容就会清空
    # 有readlines()的地方都是流,用过之后就没有了
    stdin, stdout, stderr = client.exec_command(arguments['<command>'])
    copy_out, copy_err = stdout.readlines(), stderr.readlines()
    if len(copy_out) and len(copy_err):
        output.write('%s----result:\n' % (' ' * 4))
        for i in copy_out:
            output.write('%s%s' % (' ' * 8, i))
        for i in copy_err:
            output.write('%s%s' % (' ' * 8, i), color=31)
        if not arguments['--skip-err']:    # 忽略命令执行错误的情况
            output.print_lock()
            exit(10)
    elif len(copy_out):
        output.write('%s----result:\n' % (' ' * 4))
        for i in copy_out:
            output.write('%s%s' % (' ' * 8, i))
    elif len(copy_err):
        output.write('%s----error:\n' % (' ' * 4), color=31)
        for i in copy_err:
            output.write('%s%s' % (' ' * 8, i), color=31)
        if not arguments['--skip-err']:
            client.close()
            output.print_lock()
            exit(10)
    client.close()


# ----------
# sftp_transfer() 远程传输文件的主函数
# ----------
def sftp_transfer(source_path, destination_path, method, client, output):
    """
    文件传输的 主函数
    paramiko的sftp client传输,只能单个文件作为参数,并且不会保留文件的时间信息,这两点都需要代码里额外处理
    client: paramiko.client.SSHClient object
    output:存储输出的对象
    """
    sftp = client.open_sftp()
    
    if platform.system() == 'Windows':
        '''根据put或get,将windows路径中的 \ 分隔符替换为 / '''
        if arguments["put"]:
            source_path = source_path.replace('\\', '/')
        elif arguments["get"]:
            destination_path = destination_path.replace('\\', '/')

    # -----下面定义sftp_transfer()函数所需的一些子函数-----
    def process_arg_dir(target):
        """处理目录时,检查用户输入,在路径后面加上/"""
        if not target.endswith('/'):
            target = target + '/'
        return target

    def sftp_put(src, dst, space):
        """封装put,增加相应输出,并依据m_time和size判断两端文件一致性,决定是否传输该文件"""
        if check_remote_path(dst) == 'file':
            src_stat = stat(src)
            dst_stat = sftp.stat(dst)
        else:
            src_stat = ''
            dst_stat = ''
        if (src_stat == '' and dst_stat == '') or not (floor(src_stat.st_mtime) == dst_stat.st_mtime and src_stat.st_size == dst_stat.st_size):
            try:
                sftp.put(src, dst)
                output.write('%s%s\n' % (' ' * space, src))
            except Exception as err:
                output.write('%s----Uploading %s Failed\n' % (' ' * (space-4), src), color=31)
                output.write('{}----{}\n'.format(' ' * (space-4), err), color=31)
                client.close()
                output.print_lock()
                exit(10)

    def sftp_get(src, dst, space):
        """封装get,增加相应输出,并依据m_time和size判断两端文件一致性,决定是否传输该文件"""
        if path.isfile(dst):
            src_stat = sftp.stat(src)
            dst_stat = stat(dst)
        else:
            src_stat = ''
            dst_stat = ''
        if (src_stat == '' and dst_stat == '') or not (src_stat.st_mtime == floor(dst_stat.st_mtime) and src_stat.st_size == dst_stat.st_size):
            try:
                sftp.get(src, dst)
                output.write('%s%s\n' % (' ' * space, src))
            except Exception as err:
                output.write('%s----Downloading %s Failed\n' % (' ' * (space-4), src), color=31)
                output.write('{}----{}\n'.format(' ' * (space-4), err), color=31)
                client.close()
                output.print_lock()
                exit(10)

    def sftp_transfer_rcmd(cmd=None, space=None):
        """
        在文件传输功能中,有些时候需要在远程执行一些命令来获取某些信息
        client: paramiko.client.SSHClient object
        output:存储输出的对象
        """
        stdin, stdout, stderr = client.exec_command(cmd)
        copy_out, copy_err = stdout.readlines(), stderr.readlines()
        if len(copy_err):
            for i in copy_err:
                output.write('%s----%s' % (' ' * space, i), color=31)
            output.print_lock()
            exit(10)
        elif len(copy_out):
            return copy_out

    def check_remote_path(r_path):
        """通过client对象在远程linux执行命令,来判断远程路径是否存在,是文件还是目录"""
        check_cmd = "if [ -e {0} ];then" \
                    "  if [ -d {0} ];then" \
                    "    echo directory;" \
                    "  elif [ -f {0} ];then" \
                    "    echo file;" \
                    "  fi;" \
                    "else" \
                    "  echo no_exist;" \
                    "fi".format(r_path)
        # check_cmd命令会有三种‘正常输出’directory  file  no_exist
        check_result = sftp_transfer_rcmd(cmd=check_cmd)[0].strip('\n')
        if check_result == 'directory':
            return 'directory'
        elif check_result == 'file':
            return 'file'
        else:
            return 'no_exist'

    def file_time(target, location):
        """获取源文件的atime和mtime"""
        if location == 'local':
            target_stat = stat(target)
        elif location == 'remote':
            target_stat = sftp.stat(target)
        return target_stat.st_atime, target_stat.st_mtime

    def create_dir(target, location, space):
        """将创建目录的代码集中到一个函数"""
        if location == 'local':
            try:
                output.write('%s----Create Local Dir: %s\n' % (' ' * space, target))
                makedirs(target)
            except Exception as err:
                # print_color('%s----%s' % (' ' * space, str(err)))
                output.write('%s----%s\n' % (' ' * space, str(err)), color=31)
                output.print_lock()
                exit(10)
        elif location == 'remote':
            output.write('%s----Create Remote Dir: %s\n' % (' ' * space, target))
            sftp_transfer_rcmd(cmd='mkdir -p {}'.format(target), space=space)
    # -----子函数定义完毕-----

    # -----上传逻辑-----
    if method == 'put':
        output.write('%s----Uploading %s TO %s\n' % (' ' * 4, source_path, destination_path))
        if path.isfile(source_path):
            '''判断src是文件'''
            check_remote_path_result = check_remote_path(destination_path)
            if check_remote_path_result == 'file':
                pass
            elif check_remote_path_result == 'directory':  # dst经判断为目录
                destination_path = process_arg_dir(destination_path) + path.basename(source_path)
            else:
                if not check_remote_path(path.dirname(destination_path)) == 'directory':
                    create_dir(path.dirname(destination_path), 'remote', 8)
                if destination_path.endswith('/') or destination_path.endswith('\\'):
                    destination_path = destination_path + path.basename(source_path)

            sftp_put(source_path, destination_path, 12)
            sftp.utime(destination_path, file_time(source_path, 'local'))
        elif path.isdir(source_path):
            '''判断src是目录'''
            if check_remote_path(destination_path) == 'file':
                output.write('%s----%s is file\n' % (' ' * 8, destination_path), color=31)
                output.print_lock()
                exit(10)
            source_path, destination_path = process_arg_dir(source_path), process_arg_dir(destination_path)
            for root, dirs, files in walk(source_path):
                '''通过 os.walk()函数取得目录下的所有文件,此函数默认包含 . ..的文件/目录,需要去掉'''
                for file_name in files:
                    s_file = path.join(root, file_name)  # 逐级取得每个sftp client端文件的全路径
                    if not search('.*/\..*', s_file):
                        '''过滤掉路径中包含以.开头的目录或文件'''
                        d_file = s_file.replace(source_path, destination_path, 1)  # 由local_file取得每个远程文件的全路径
                        d_path = path.dirname(d_file)
                        if check_remote_path(d_path) == 'directory':
                            sftp_put(s_file, d_file, 12)
                        else:
                            create_dir(d_path, 'remote', 8)
                            sftp_put(s_file, d_file, 12)

                        sftp.utime(d_file, file_time(s_file, 'local'))
        else:
            output.write('%s%s is not exist\n' % (' ' * 8, source_path), color=31)
            output.print_lock()
            exit(10)

    # -----下载逻辑-----
    elif method == 'get':
        output.write('%s----Downloading %s TO %s\n' % (' ' * 4, source_path, destination_path))
        check_remote_path_result = check_remote_path(source_path)

        if check_remote_path_result == 'file':
            '''判断source_path是文件'''
            if path.isfile(destination_path):  # destination_path为文件
                pass
            elif path.isdir(destination_path):  # destination_path为目录
                destination_path = process_arg_dir(destination_path) + path.basename(source_path)
            else:
                if not path.isdir(path.dirname(destination_path)):
                    create_dir(path.dirname(destination_path), 'local', 8)
                if destination_path.endswith('/') or destination_path.endswith('\\'):
                    destination_path = destination_path + path.basename(source_path)

            sftp_get(source_path, destination_path, 12)
            utime(destination_path, file_time(source_path, 'remote'))
        elif check_remote_path_result == 'directory':
            '''判断source_path是目录'''
            if path.isfile(destination_path):
                output.write('%s----%s is file\n' % (' ' * 8, destination_path), color=31)
                output.print_lock()
                exit(10)
            source_path, destination_path = process_arg_dir(source_path), process_arg_dir(destination_path)

            def process_sftp_dir(path_name):
                """
                此函数递归处理sftp server端的目录和文件,并在client端创建所有不存在的目录,然后针对每个文件在两端的全路径执行get操作.
                path_name第一次的引用值应该是source_path的值
                """
                d_path = path_name.replace(source_path, destination_path, 1)
                if not path.exists(d_path):  # 若目标目录不存在则创建
                    create_dir(d_path, 'local', 8)
                for name in (i for i in sftp.listdir(path=path_name) if not i.startswith('.')):
                    '''去掉以.开头的文件或目录'''
                    s_file = path.join(path_name, name)  # 源文件全路径 
                    d_file = s_file.replace(source_path, destination_path, 1)  # 目标端全路径
                    chk_r_path_result = check_remote_path(s_file)
                    if chk_r_path_result == 'file':  # 文件
                        sftp_get(s_file, d_file, 12)
                        utime(d_file, file_time(s_file, 'remote'))
                    elif chk_r_path_result == 'directory':  # 目录
                        process_sftp_dir(s_file)  # 递归调用本身

            process_sftp_dir(source_path)
        else:
            output.write('%s%s is not exist\n' % (' ' * 8, source_path), color=31)
            output.print_lock()
            exit(10)
    client.close()


def process_single_server(server_name, server_ip, port):
    """处理一台server的逻辑"""
    local_data = threading.local()  # 可以看到多线程情况下,确实是不同的OutputText实例,说明threading.local()起到了预期作用
    local_data.output = OutputText()
    local_data.output.write('\n----{}\n'.format(server_name))  # 这行写入的数据可以在多线程环境下正常打出
    client = create_sshclient(server_ip, port, local_data.output)
    if client == 'error':
        if not arguments['--skip-err']:
            exit(10)
        else:
            return
    # 区别处理 cmd put get参数
    if arguments['cmd']:
        run_command(client, local_data.output)
    elif arguments['put']:
        sftp_transfer(arguments['<src>'], arguments['<dst>'], 'put', client, local_data.output)
    elif arguments['get']:
        sftp_transfer(arguments['<src>'], arguments['<dst>'], 'get', client, local_data.output)
    # 前面的逻辑可以并行,打印必须要加锁实现串行
    local_data.output.print_lock()


if __name__ == "__main__":
    global_lock = threading.Lock()
    try:
        arguments = docopt(__doc__)
        conf_dict = yaml.load(open(arguments['-c']))
        threads_list = []
        for server_name, server_ip, port in get_ip_port(conf_dict, arguments['<targets>']):
            '''循环处理每个主机'''
            t = threading.Thread(target=process_single_server, args=(server_name, server_ip, port), daemon=True)
            t.start()
            if not arguments['--parallel']:
                t.join()  # (串行)谁对t线程发起join,谁就阻塞直到t线程执行完
            threads_list.append(t)  # 按顺序进队
        for t in threads_list:
            t.join()  # 在这里join(),程序依然是并行
    except KeyboardInterrupt:
        '''多线程环境下,thread对象要设置daemon=True同时要有join()操作,才能优雅的捕捉并处理'''
        print_color('\n----bye----')
        exit(-10)
    except Exception as err:
        print(err)
        exit(10)
