#!/bin/env python3
# coding:utf-8
"""
by ljk 20160704
"""
from paramiko import SSHClient, AutoAddPolicy
from os import path, walk, makedirs
from re import split, match, search
from sys import exit
from argparse import ArgumentParser, RawTextHelpFormatter

# ----------
# get_args()函数通过argparse模块的ArgumentParser类来生成帮助信息并获取命令行参数
# 生成一个全局变量字典对象args，保存处理过的命令行参数
# ----------
def get_args():
    """实例化类，formatter_class参数允许help信息以自定义的格式显示"""
    parser = ArgumentParser(description="This is a tool for execute command(s) on remote server(s) or get/put file(s) from/to the remote server(s)\nNotice: please always use '/' as path separater!!!",formatter_class =RawTextHelpFormatter,epilog="Notice:\n  If any options use more than once,the last one will overwrite the previous")
    parser.add_argument('-u',metavar='USER',dest='user',help="remote username",required=True)
    parser.add_argument('-p',metavar='PASSWORD',dest='passwd',help="user's password")
    parser.add_argument('--pkey',nargs='?',metavar='PRIVATE KEY',dest='pkey',help="local private key,if value not followed by this option,the default is: ~/.ssh/id_rsa",default=None,const='%s/.ssh/id_rsa' % path.expanduser('~'))
    parser.add_argument('--skip-err',nargs='?',metavar='SIKP ERRORS',dest='skip_err',help="without this option: once error(s) occur in one server, this script will stop",default=None,const=True)
    parser.add_argument('--server', metavar='SERVER_INFO_FILE', help="file include the remote server's information\nwith the format of 'name-ip:port',such as 'web1-192.168.1.100:22',one sever one line", required=True)
    remote_command = parser.add_argument_group('remote command','options for running remote command')
    remote_command.add_argument('--cmd',metavar='“COMMAND”',dest='cmd',help="command run on remote server,multiple commands sperate by ';'")
    sftp = parser.add_argument_group('sftp','options for running sftp')
    sftp.add_argument('--put',metavar='',help="transfer from local to remote",nargs=2)
    sftp.add_argument('--get',metavar='',help="transfer from remote to local",nargs=2)
    # 全局字典 键(add_argument()中的dest):值(用户输入)
    # vars将Namespace object转换成dict object
    global args
    args = vars(parser.parse_args())
    # 判断 --cmd  --put  --get 三个参数的唯一性
    # 清除掉args字典中值为None的项.argparse默认给不出现的值赋值None
    n = 0
    for i in ('cmd','put','get'):
        if i in args:
            if args[i] is None:
                del args[i]
            else:
                n+=1
    if n > 1:
        print('\n  Only one of the "--cmd --put --get" can be used!')
        exit(10)

def get_ip_port(fname):
    """从制定文件(特定格式)中，取得主机名/主机ip/端口"""
    try:
        fobj = open(fname,'r')
    except Exception as err:
        print(err)
        exit(10)
    for line in fobj.readlines():
        if line != '\n' and not   match('#',line):    # 过滤空行和注释行
            list_tmp =   split('[-:]',line)
            server_name = list_tmp[0]
            server_ip = list_tmp[1]
            port = int(list_tmp[2])
            yield (server_name,server_ip,port)

def create_sshclient(server_ip,port):
    """根据命令行提供的参数，建立到远程server的ssh链接.这里本在run_command()函数内部。
    摘出来的目的是为了让sftp功能也通过sshclient对象来创建sftp对象，因为初步观察t.connect()方法在使用key时有问题"""
    global client
    client = SSHClient()
    client.set_missing_host_key_policy(AutoAddPolicy())
    try:
        client.connect(server_ip,port=port,username=args['user'],password=args['passwd'],key_filename=args['pkey'])
    except Exception as err:    # 有异常，打印异常，并返回'error'
        print('{}----{} error: {}'.format(' '*4,server_ip,err))
        return 'error'

# ----------
# run_command()执行远程命令
# ----------
def run_command():
    """执行远程命令的主函数"""
    # stdout 假如通过分号提供单行的多条命令，所有命令的输出（在linux终端会输出的内容）都会存储于stdout
    # 据观察，下面三个变量的特点是无论"如何引用过一次"之后，其内容就会清空
    # 有readlines()的地方都是流，用过之后就没有了
    stdin,stdout,stderr = client.exec_command(args['cmd'])
    copy_out,copy_err = stdout.readlines(),stderr.readlines()
    if len(copy_out) != 0:
        print('%s----result:' % (' '*8))
        for i in copy_out:
            print('%s%s' % (' '*12,i),end='')
    elif len(copy_err) != 0:
        print('%s----error:' % (' '*8))
        for i in copy_err:
            print('%s%s' % (' '*12,i),end='')
        if args['skip_err'] == None:
            exit(10)
    client.close()

# ----------
# sftp_transfer() 远程传输文件的主函数
# ----------
def sftp_transfer(source_path,destination_path,method):
    """文件传输的 主函数"""
    sftp = client.open_sftp()

    # 下面定义sftp_transfer()函数所需的一些子函数
    def str_to_raw(s):
        """
        !!此函数暂未使用，参数中的目录强制使用'/'作为分隔符!!
        借用网友的代码，将会被反斜杠转义的字符做转换.将\转换为\\，这里的转换还不全，比如对'\123'这样的还无法转换成'\\123'
        """
        raw_map = {8:r'\b', 7:r'\a', 12:r'\f', 10:r'\n', 13:r'\r', 9:r'\t', 11:r'\v'}
        return r''.join(i if ord(i) > 32 else raw_map.get(ord(i), i) for i in s)

    def process_arg_dir(src,dst):
        """处理目录时，自动检查用户输入，并在s_path和d_path后面都加上/"""
        if not src.endswith('/'):
            src = src + '/'
        if not dst.endswith('/'):
            dst = dst + '/'
        return src,dst

    def sftp_put(src, dst, space):
        """封装"""
        try:
            sftp.put(src, dst)
            print('%s%s' % (' ' * space, src))
        except Exception as err:
            print('%s----Uploading %s Failed' % (' ' * space, src))
            print('{}----{}'.format(' ' * space, err))
            exit(10)

    def sftp_get(src, dst, space):
        try:
            sftp.get(src, dst)
            print('%s%s' % (' ' * space, src))
        except Exception as err:
            print('%s----Downloading %s Failed' % (' ' * space, src))
            print('{}----{}'.format(' ' * space, err))
            exit(10)

    def sftp_transfer_rcmd(cmd=None,space=None):
        stdin,stdout,stderr = client.exec_command(cmd)
        copy_out, copy_err = stdout.readlines(), stderr.readlines()
        if len(copy_err) != 0:
            for i in copy_err:
                print('%s----%s' % (' '*space,i),end='')
            exit(10)
        else:
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
    # 子函数定义完毕

    # 上传逻辑
    if method == 'put':
        print('%s----Uploading %s TO %s' % (' '*4,source_path,destination_path))
        if  path.isfile(source_path):    # 判断是文件
            if destination_path.endswith('/'):
                """
                put和get方法默认只针对文件，且都必须跟上文件名，否则会报错.
                这里多加一层判断实现了目标路径可以不加文件名
                """
                sftp_transfer_rcmd(cmd='mkdir -p {}'.format(destination_path),space=4)    # 若目标路径不存在，则创建
                destination_path = destination_path +  path.basename(source_path)
                sftp_put(source_path, destination_path, 8)
            else:
                sftp_transfer_rcmd(cmd='mkdir -p {}'.format( path.dirname(destination_path)), space=4)
        elif  path.isdir(source_path):   # 判断是目录
            source_path,destination_path = process_arg_dir(source_path,destination_path)
            for root, dirs, files in  walk(source_path):
                """通过 os.walk()函数取得目录下的所有文件,此函数默认包含 . ..的文件/目录,需要去掉"""
                for file_name in files:
                    s_file =  path.join(root,file_name).replace('\\','/')    # 逐级取得每个sftp client端文件的全路径,并将路径中的\换成/
                    if not   search('.*/\..*', s_file):
                        """过滤掉路径中包含以.开头的目录或文件"""
                        d_file = s_file.replace(source_path,destination_path,1)    # 由local_file取得每个远程文件的全路径
                        d_path =  path.dirname(d_file)
                        check_remote_path_result = check_remote_path(d_path)
                        if check_remote_path_result == 'directory':
                            sftp_put(s_file, d_file, 12)  # 目标目录存在，直接上传
                        elif check_remote_path_result == 'no_exist':
                            print('%s----Create Remote Dir: %s' % (' ' * 8,  path.dirname(d_file)))
                            sftp_transfer_rcmd(cmd='mkdir -p {}'.format(d_path))
                            sftp_put(s_file, d_file, 12)
                        else:
                            print('{}----the {} is file'.format(' ' * 8, d_path))
                            exit(10)
        else:
            print('%s%s is not exist' % (' '*8,source_path))
            exit(10)

    # 下载逻辑
    elif method == 'get':
        print('%s----Downloading %s TO %s' % (' '*4, source_path, destination_path))
        check_remote_path_result = check_remote_path(source_path)
        if check_remote_path_result == 'file':    # 判断是文件
            if  path.isfile(destination_path):
                sftp_get(source_path, destination_path, 8)
            else:    # 参数中的'目标路径'为目录或不存在
                try:
                    makedirs(destination_path)
                    sftp_get(source_path,  path.join(destination_path, path.basename(source_path)).replace('\\','/'), 8)
                except Exception as err:
                    print('%s----Create %s error' % (' '*4,destination_path))
                    print('{}{}'.format(' '*8,err))
                    exit(10)
            sftp_get(source_path,destination_path,8)
        elif check_remote_path_result == 'directory':    # 判断是目录
            source_path, destination_path = process_arg_dir(source_path,destination_path)
            
            def process_sftp_dir(path_name):
                #source_path, destination_path = process_arg_dir(source_path,destination_path)
                """
                此函数递归处理sftp server端的目录和文件,并在client端创建所有不存在的目录,然后针对每个文件在两端的全路径执行get操作.
                path_name第一次的引用值应该是source_path的值
                """
                d_path = path_name.replace(source_path,destination_path,1)
                if not  path.exists(d_path):    # 若目标目录不存在则创建
                    print('%s----Create Local Dir: %s' % (' '*8,d_path))
                    try:
                         makedirs(d_path)    # 递归创建不存在的目录
                    except Exception as err:
                        print('%s----Create %s Failed' % (' '*8,d_path))
                        print('{}----{}'.format(' '*8,err))
                        exit(10)
                for name in (i for i in sftp.listdir(path=path_name) if not i.startswith('.')):
                    """去掉以.开头的文件或目录"""
                    s_file =  path.join(path_name,name).replace('\\','/')    # 在win环境下组合路径所用的'\\'换成'/'
                    d_file = s_file.replace(source_path,destination_path,1)    # 目标端全路径
                    chk_r_path_result = check_remote_path(s_file)
                    if chk_r_path_result == 'file':    # 文件
                        sftp_get(s_file,d_file,12)
                    elif chk_r_path_result == 'directory':    # 目录
                        process_sftp_dir(s_file)    # 递归调用本身
            process_sftp_dir(source_path)
        else:
            print('%s%s is not exist' % (' ' * 8, source_path))
            exit(10)
    client.close()

if __name__ == "__main__":
    try:
        get_args()
        print(args)
        exit(100)
        for server_name,server_ip,port in get_ip_port(args['server']):    #循环处理每个主机
            print('\n--------%s' % server_name)
            if create_sshclient(server_ip,port) == 'error':
                continue
            # 区别处理 --cmd --put --get参数
            if 'cmd' in args:
                run_command()
            elif 'put' in args:
                sftp_transfer(args['put'][0],args['put'][1],'put')
            elif 'get' in args:
                sftp_transfer(args['get'][0],args['get'][1],'get')
    except KeyboardInterrupt:
        print('\n-----bye-----')
