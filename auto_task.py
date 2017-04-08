#!/bin/env python3
# coding:utf-8
"""
Usage:
  auto_task [options] cmd <comand> [--skip-err]
  auto_task [options] get <src> <dst>
  auto_task [options] put <src> <dst>

Options:
  -h --help             Show this screen.
  -u <user>             Remote username [default: root]
  -p <password>         User's password
  --pkey <private-key>  Local private key [default: /root/.ssh/id_rsa]
  --server <server_info_file>  
                        File include the remote server's information.
                        With the format of 'name-ip:port', such as 'web1-192.168.1.100:22',one server one line
  --skip-err            Use with cmd, if sikp any server's error and continue process the other servers [default: False]

  cmd                 run command on remote server(s),multiple commands sperate by ';'
  get                 Transfer from remote to local. Transport mechanism similar to rsync.
  put                 Transfer from local to remote. Transport mechanism similar to rsync.

  Notice:      cmd, get, put can only use one at once
  For Windows: Always use double quotes for quote something
               It's highly recommend that with get or put in Windows,always use '/' instead of '\\'
"""

"""
by ljk 20160704
update at 20170111
"""
from docopt import docopt
from paramiko import SSHClient, AutoAddPolicy
from os import path, walk, makedirs, stat, utime
from re import split, match, search
from sys import exit
import platform
from math import floor

def get_ip_port(fname):
    """从制定文件(特定格式)中，取得主机名/主机ip/端口"""
    try:
        with open(fname, 'r') as fobj:
            for line in fobj.readlines():
                if line != '\n' and not match('#', line):  # 过滤空行和注释行
                    list_tmp = split('[-:]', line)
                    server_name = list_tmp[0]
                    server_ip = list_tmp[1]
                    port = int(list_tmp[2])
                    yield (server_name, server_ip, port)
    except Exception as err:
        print(err)
        exit(10)

def create_sshclient(server_ip, port):
    """根据命令行提供的参数，建立到远程server的ssh链接.这段本应在run_command()函数内部。
    摘出来的目的是为了让sftp功能也通过sshclient对象来创建sftp对象，因为初步观察t.connect()方法在使用key时有问题"""
    global client
    client = SSHClient()
    client.set_missing_host_key_policy(AutoAddPolicy())
    try:
        client.connect(server_ip, port=port, username=arguments['-u'], password=arguments['-p'], key_filename=arguments['--pkey'])
    except Exception as err:  # 有异常，打印异常，并返回'error'
        print('{}----{} ssh connect error: {}'.format(' ' * 4, server_ip, err))
        return 'error'

# ----------
# run_command()执行远程命令
# ----------
def run_command():
    """执行远程命令的主函数"""
    # stdout 假如通过分号提供单行的多条命令，所有命令的输出（在linux终端会输出的内容）都会存储于stdout
    # 据观察，下面三个变量的特点是无论"如何引用过一次"之后，其内容就会清空
    # 有readlines()的地方都是流，用过之后就没有了
    stdin, stdout, stderr = client.exec_command(arguments['<comand>'])
    copy_out, copy_err = stdout.readlines(), stderr.readlines()
    if len(copy_out) and len(copy_err):
        print('%s----result:' % (' ' * 8))
        for i in copy_out:
            print('%s%s' % (' ' * 12, i), end='')
        for i in copy_err:
            print('%s%s' % (' ' * 12, i), end='')
        if not arguments['--skip-err']:    # 忽略命令执行错误的情况
            exit(10)
    elif len(copy_out):
        print('%s----result:' % (' ' * 8))
        for i in copy_out:
            print('%s%s' % (' ' * 12, i), end='')            
    elif len(copy_err):
        print('%s----error:' % (' ' * 8))
        for i in copy_err:
            print('%s%s' % (' ' * 12, i), end='')
        if not arguments['--skip-err']:
            exit(10)
    client.close()

# ----------
# sftp_transfer() 远程传输文件的主函数
# ----------
def sftp_transfer(source_path, destination_path, method):
    """文件传输的 主函数
        paramiko的sftp client传输，只能单个文件作为参数，并且不会保留文件的时间信息，这两点都需要代码里额外处理
    """
    sftp = client.open_sftp()
    
    if platform.system() == 'Windows':
        """根据put或get,将windows路径中的'\'分隔符替换为'/'"""
        if arguments["put"]:
            source_path = source_path.replace('\\', '/')
        elif arguments["get"]:
            destination_path = destination_path.replace('\\', '/')

    # -----下面定义sftp_transfer()函数所需的一些子函数-----
    def process_arg_dir(target):
        """处理目录时，检查用户输入，在路径后面加上/"""
        if not target.endswith('/'):
            target = target + '/'
        return target

    def sftp_put(src, dst, space):
        """封装put，增加相应输出，并依据m_time和size判断两端文件一致性，决定是否传输该文件"""
        if check_remote_path(dst) == 'file':
            src_stat = stat(src)
            dst_stat = sftp.stat(dst)
        else:
            src_stat = ''
            dst_stat = ''
        if (src_stat == '' and dst_stat == '') or not (floor(src_stat.st_mtime) == dst_stat.st_mtime and src_stat.st_size == dst_stat.st_size):
            try:
                sftp.put(src, dst)
                print('%s%s' % (' ' * space, src))
            except Exception as err:
                print('%s----Uploading %s Failed' % (' ' * (space-4), src))
                print('{}----{}'.format(' ' * (space-4), err))
                exit(10)

    def sftp_get(src, dst, space):
        """封装get，增加相应输出，并依据m_time和size判断两端文件一致性，决定是否传输该文件"""
        if path.isfile(dst):
            src_stat = sftp.stat(src)
            dst_stat = stat(dst)
        else:
            src_stat = ''
            dst_stat = ''
        if (src_stat == '' and dst_stat == '') or not (src_stat.st_mtime == floor(dst_stat.st_mtime) and  src_stat.st_size == dst_stat.st_size):
            try:
                sftp.get(src, dst)
                print('%s%s' % (' ' * space, src))
            except Exception as err:
                print('%s----Downloading %s Failed' % (' ' * (space-4), src))
                print('{}----{}'.format(' ' * (space-4), err))
                exit(10)

    def sftp_transfer_rcmd(cmd=None, space=None):
        """在文件传输功能中，有些时候需要在远程执行一些命令来获取某些信息"""
        stdin, stdout, stderr = client.exec_command(cmd)
        copy_out, copy_err = stdout.readlines(), stderr.readlines()
        if len(copy_err):
            for i in copy_err:
                print('%s----%s' % (' ' * space, i), end='')
            exit(10)
        elif len(copy_out):
            return copy_out

    def check_remote_path(r_path):
        """通过client对象在远程linux执行命令，来判断远程路径是否存在，是文件还是目录"""
        check_cmd = 'if [ -e {0} ];then if [ -d {0} ];then echo directory;elif [ -f {0} ];then echo file;fi;else echo no_exist;fi'.format(r_path)
        # check_cmd命令会有三种‘正常输出’directory  file  no_exist
        check_result = sftp_transfer_rcmd(cmd=check_cmd)[0].strip('\n')
        if check_result == 'directory':
            return 'directory'
        elif check_result == 'file':
            return 'file'
        else:
            return 'no_exist'

    def file_time(target,location):
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
                print('%s----Create Local Dir: %s' % (' ' * space, target))
                makedirs(target)
            except Exception as err:
                print('%s----%s' % (' ' * space, str(err)))
                exit(10)
        elif location == 'remote':
            print('%s----Create Remote Dir: %s' % (' ' * space, target))
            sftp_transfer_rcmd(cmd='mkdir -p {}'.format(target), space=space)
    
    # -----子函数定义完毕-----

    # -----上传逻辑-----
    if method == 'put':
        print('%s----Uploading %s TO %s' % (' ' * 4, source_path, destination_path))
        if path.isfile(source_path):
            '''判断src是文件'''
            if check_remote_path(destination_path) == 'file':
                pass
            elif check_remote_path(destination_path) == 'directory':  # dst经判断为目录
                destination_path = process_arg_dir(destination_path) + path.basename(source_path)
            else:
                create_dir(path.dirname(destination_path), 'remote', 8)
                if destination_path.endswith('/') or destination_path.endswith('\\'):
                    destination_path = destination_path + path.basename(source_path)

            sftp_put(source_path, destination_path, 12)
            sftp.utime(destination_path, file_time(source_path, 'local'))

        elif path.isdir(source_path):
            '''判断src是目录'''
            if check_remote_path(destination_path) == 'file':
                print('%s----%s is file' % (' ' * 8, destination_path))
                exit(10)
            source_path, destination_path = process_arg_dir(source_path), process_arg_dir(destination_path)
            for root, dirs, files in walk(source_path):
                """通过 os.walk()函数取得目录下的所有文件,此函数默认包含 . ..的文件/目录,需要去掉"""
                for file_name in files:
                    s_file = path.join(root, file_name)  # 逐级取得每个sftp client端文件的全路径
                    if not search('.*/\..*', s_file):
                        """过滤掉路径中包含以.开头的目录或文件"""
                        d_file = s_file.replace(source_path, destination_path, 1)  # 由local_file取得每个远程文件的全路径
                        d_path = path.dirname(d_file)
                        check_remote_path_result = check_remote_path(d_path)
                        if check_remote_path_result == 'directory':
                            sftp_put(s_file, d_file, 12)
                        else:
                            create_dir(d_path, 'remote', 8)
                            sftp_put(s_file, d_file, 12)

                        sftp.utime(d_file, file_time(s_file, 'local'))
        else:
            print('%s%s is not exist' % (' ' * 8, source_path))
            exit(10)

    # -----下载逻辑-----
    elif method == 'get':
        print('%s----Downloading %s TO %s' % (' ' * 4, source_path, destination_path))
        check_remote_path_result = check_remote_path(source_path)

        if check_remote_path_result == 'file':
            '''判断source_path是文件'''
            if path.isfile(destination_path):  # destination_path为文件
                pass
            elif path.isdir(destination_path):  # destination_path为目录
                destination_path = process_arg_dir(destination_path) + path.basename(source_path)
            else:
                create_dir(path.dirname(destination_path), 'local', 8)
                if destination_path.endswith('/') or destination_path.endswith('\\'):
                    destination_path = destination_path + path.basename(source_path)

            sftp_get(source_path, destination_path, 12)
            utime(destination_path, file_time(source_path, 'remote'))

        elif check_remote_path_result == 'directory':
            '''判断source_path是目录'''
            if path.isfile(destination_path):
                print('%s----%s is file' % (' ' * 8, destination_path))
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
                    """去掉以.开头的文件或目录"""
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
            print('%s%s is not exist' % (' ' * 8, source_path))
            exit(10)
    client.close()

if __name__ == "__main__":
    arguments = docopt(__doc__)
    #print(arguments)
    try:
        for server_name, server_ip, port in get_ip_port(arguments['--server']):  # 循环处理每个主机
            print('\n--------%s' % server_name)
            if create_sshclient(server_ip, port) == 'error':
                continue
            # 区别处理 cmd put get参数
            if arguments['cmd']:
                run_command()
            elif arguments['put']:
                sftp_transfer(arguments['<src>'], arguments['<dst>'], 'put')
            elif arguments['get']:
                sftp_transfer(arguments['<src>'], arguments['<dst>'], 'get')
    except KeyboardInterrupt:
        print('\n-----bye-----')    
