# Linux 常用操作与排查

这篇笔记按实际任务组织常用命令：先判断资源瓶颈，再定位进程、权限或网络问题。命令示例基于 Linux；安装方式、服务名和防火墙工具因发行版而异。示例中的 PID、地址、网卡名和路径都应替换为实际值。

| 遇到的问题 | 先检查 | 继续定位 |
| --- | --- | --- |
| 系统变慢 | `uptime`、`top` | `free -h`、`vmstat 1`、`iostat -x 1` |
| 磁盘写不进去 | `df -h`、`df -i` | 用 `du -sh 目录` 定位占用 |
| 找不到或无法结束进程 | `pgrep -a 名称`、`ps` | `kill`、`systemctl` |
| 文件访问被拒绝 | `ls -ld`、`ls -l` | 检查所有者及路径上各级目录的权限 |
| 服务端口无法访问 | `ss -lntp` | 本机访问、远程连通性、防火墙 |

## 1. 查看资源使用情况

### 1.1 先看负载和进程

```bash
uptime
```

`uptime` 的最后三个数字是过去 1、5、15 分钟的平均负载。负载统计的是正在运行、等待 CPU 或处于不可中断等待（常见于 I/O）的任务，**不是 CPU 使用率**。解释负载时还要结合 CPU 数量和后续指标，不能仅凭一个数字判断瓶颈。

```bash
top                 # 实时查看系统与进程；按 q 退出
top -u username     # 只看指定用户的进程
top -p 12345        # 只看指定 PID
ps aux              # 一次性列出所有用户的进程
ps -ef              # 以另一种完整格式列出进程
```

`top` 适合观察变化，`ps` 适合记录某一时刻的状态。`top` 中可结合 `%CPU`、`%MEM` 和进程状态找出占用较高的进程；单个瞬时值不足以说明长期问题。`htop` 提供交互界面和树状视图，但通常需要额外安装，例如 Debian/Ubuntu 使用 `sudo apt install htop`。

### 1.2 看内存和交换

```bash
free -h
vmstat 1
```

`free` 展示物理内存和交换空间。判断是否还有可用内存时优先看 `available`，不要把 `free` 很小直接等同于内存不足：Linux 会利用空闲内存做缓存。`-m` 和 `-g` 分别以 MiB、GiB 显示。

`vmstat 1` 每秒报告一次 CPU、内存、交换和 I/O 统计。关注持续的交换读写（`si`、`so`）和等待 I/O 的 CPU 时间（`wa`），再结合应用表现继续排查。首行通常反映开机以来的平均值，观察实时变化时重点看后续行。

### 1.3 看磁盘空间、inode 和 I/O

```bash
df -h                  # 查看已挂载文件系统的空间使用
df -i                  # 查看 inode 使用情况
du -sh /path/to/dir    # 汇总指定目录的磁盘占用
iostat -x 1            # 每秒查看一次设备 I/O 扩展统计
```

`df` 看文件系统整体，`du` 看目录或文件。两者统计对象不同，数值未必相等。遇到“磁盘已满”时同时看 `df -h` 与 `df -i`：空间尚有余量但 inode 耗尽，也可能无法创建新文件。`du` 默认递归列出子目录；`-s` 只显示汇总，`-h` 使用易读单位。

例如，`df -h` 的 `Use%` 接近满额时，按挂载点定位占用目录；若空间尚有余量而 `df -i` 的 `IUse%` 已满，应优先排查大量小文件。清理前先确认文件用途及所属服务。

`iostat` 通常来自 `sysstat` 软件包。持续较高的 I/O 等待或设备响应时间值得进一步检查，但不要只凭单个 `%util` 值判定磁盘故障；应结合设备类型、吞吐量和应用延迟。

### 1.4 看历史趋势

```bash
sar -u    # CPU 历史数据
sar -r    # 内存历史数据
```

`sar` 适合回答“刚才是否也很慢”。历史数据依赖 `sysstat` 已安装并启用采集；未启用时可能没有过去的记录。

## 2. 查找与管理进程

### 2.1 找到正确的进程

```bash
pgrep -a nginx          # 按名称查找，并显示 PID 与命令行
pgrep -u username       # 查找指定用户的进程
ps -p 12345 -f          # 查看指定 PID 的详细信息
```

先确认 PID 和命令行，再决定是否终止。进程名可能对应多个实例，`killall nginx` 会向所有匹配名称的进程发信号，使用前应确认影响范围。

### 2.2 发送信号与调整调度优先级

```bash
kill 12345              # 默认发送 TERM，让进程有机会清理并退出
kill -9 12345           # 发送 KILL，仅在无法正常退出时考虑
nice -n 10 command      # 以 nice 值 10 启动命令
renice -n 15 -p 12345   # 调整已运行进程的 nice 值
```

`kill` 的作用是发送信号，不等于立即结束进程。nice 值越大，进程通常获得越低的 CPU 调度优先级；它不限制进程可使用的 CPU 上限。修改其他用户的进程或提高优先级可能需要相应权限。

### 2.3 管理由 systemd 托管的服务

```bash
systemctl status nginx
journalctl -u nginx -n 50 --no-pager  # 查看最近 50 条服务日志
sudo systemctl start nginx
sudo systemctl stop nginx
```

`systemctl` 操作的是服务单元，不等同于直接操作某个 PID。服务反复退出时，先看状态和日志，再判断是否需要重启；服务名应以当前系统安装的单元为准。

## 3. 文件与目录权限

### 3.1 先读懂权限和所有者

```bash
ls -l file.txt       # 查看文件权限、所有者和所属组
ls -ld /path/to/dir  # 查看目录自身，而非其内容
```

例如 `-rwxr-xr-- 1 user group ... file.txt` 中，第一个字符表示文件类型，后面三组分别是所有者、所属组、其他用户的权限。`u`、`g`、`o` 分别对应这三类；访问结果还取决于路径上各级目录的权限，不能只看目标文件。

| 权限 | 普通文件 | 目录 |
| --- | --- | --- |
| `r`（读） | 读取内容 | 列出条目名称 |
| `w`（写） | 修改内容 | 添加、删除或重命名条目，通常还需要 `x` |
| `x`（执行/搜索） | 执行具备有效程序格式的文件 | 遍历目录，访问已知名称的条目 |

删除文件主要由其**所在目录**的权限决定；只给文件本身写权限，并不代表可以删除它。

### 3.2 用 `chmod` 修改权限

符号模式适合只改某一类权限；数字模式适合设置完整的普通权限位。数字中 `r=4`、`w=2`、`x=1`，三位依次表示所有者、组、其他用户。

```bash
chmod u+x script.sh      # 给所有者增加执行权限
chmod g-w file.txt       # 移除组写权限
chmod o=r file.txt       # 将其他用户权限设为只读
chmod 644 file.txt       # rw-r--r--
chmod 600 secret.txt     # rw-------
chmod 755 script.sh      # rwxr-xr-x
```

`chmod -R` 会递归作用于目录内的文件和子目录。若只想给所有者补齐常用权限，可使用：

```bash
chmod -R u+rwX /path/to/dir
```

大写 `X` 仅对目录或原本已有执行权限的文件添加执行权限，避免把所有普通文件改成可执行。递归操作前应确认路径和权限需求。

### 3.3 默认权限与所有权

```bash
umask             # 查看当前 shell 的权限掩码
chown user:group file.txt
chgrp group file.txt
```

新文件与新目录的权限会受创建程序传入的权限、`umask` 及可能存在的默认 ACL 影响。常见示例中，程序以 `0666` 创建普通文件、`0777` 创建目录，`umask 022` 分别得到 `0644` 和 `0755`；这只是示例，不是所有环境的固定结果。`chmod` 改权限，`chown`、`chgrp` 改所有者和所属组。

## 4. 排查服务端口

端口无法访问时，按“服务是否监听 → 本机是否可达 → 远程是否可达”的顺序检查。修改网卡 IP 地址是另一类操作，通常不需要为了开放端口而执行。

### 4.1 确认服务监听的地址与端口

```bash
sudo ss -lntp       # TCP 监听端口及关联进程
ss -lun             # UDP 套接字
```

`ss` 中 `-l` 表示监听、`-n` 保留数字地址和端口、`-t`/`-u` 分别选 TCP/UDP、`-p` 显示进程。查看其他用户的进程可能需要 `sudo`。

例如，输出中的 `Local Address:Port` 若为 `127.0.0.1:8080`，表示该服务绑定到本机回环地址；若为 `0.0.0.0:8080`，表示绑定到所有 IPv4 地址。实际是否允许远程访问，还取决于防火墙和网络路径。

如果服务只绑定 `127.0.0.1`，它只能从本机访问；要供其他机器访问，需要检查服务自身的监听地址配置。若看不到目标端口，先检查服务状态及其配置，再看防火墙。看到监听端口只说明本机有对应套接字，不能证明远程可达。

### 4.2 验证本机与远程连通性

```bash
nc -zv 127.0.0.1 8080       # 在服务器上测试本机 TCP 连接
nc -zv your-server-ip 8080  # 在客户端测试到服务器的 TCP 连接
curl -I http://127.0.0.1:8080/  # 对 HTTP 服务检查响应头
```

本机连接成功、远程失败时，依次检查监听地址、主机防火墙、云平台安全组和网络路由。`nc -zv` 测试的是 TCP 连接能否建立；应用是否正常响应还需用相应协议的客户端验证，例如 HTTP 服务可用浏览器或 `curl`。

### 4.3 按发行版配置服务与防火墙

以 Apache 监听 8080/TCP 为例，先在服务配置中设置 `Listen 8080`。Debian/Ubuntu 常见配置文件是 `/etc/apache2/ports.conf`，服务名是 `apache2`；RHEL 系常见配置文件是 `/etc/httpd/conf/httpd.conf`，服务名是 `httpd`。按实际发行版修改并重启对应服务，再回到 `ss` 确认监听。

只使用当前系统实际启用的防火墙管理工具，并确认规则作用于正确的 zone 或接口：

| 工具 | 查看状态或规则 | 放行 8080/TCP 的示例 |
| --- | --- | --- |
| `ufw`（常见于 Ubuntu） | `sudo ufw status` | `sudo ufw allow 8080/tcp` |
| `firewalld` | `sudo firewall-cmd --get-active-zones` | `sudo firewall-cmd --zone=public --add-port=8080/tcp --permanent`，随后执行 `sudo firewall-cmd --reload` |
| `iptables` | `sudo iptables -L -n` | `sudo iptables -A INPUT -p tcp --dport 8080 -j ACCEPT` |

`firewalld` 的 `public` 只是示例，先确认目标网卡所在 zone。`iptables -A` 追加运行时规则，实际效果受已有规则顺序影响；持久化方式取决于发行版。远程管理服务器时，先确认管理端口仍可访问，再调整防火墙。

### 4.4 网卡地址与旧工具

```bash
ip addr show      # 查看网卡与 IP 地址
ip route show     # 查看路由
```

只有在服务器地址或路由本身有问题时，才需修改网卡配置。`ip addr add 192.168.1.100/24 dev eth0` 只是临时添加地址的示例，`eth0` 也未必是实际网卡名；持久化应使用发行版的网络管理工具。远程修改接口可能中断当前连接。

`ifconfig` 和 `netstat` 属于较旧的工具，有些系统需要额外安装。常见对应关系：`ip addr show` 对应查看接口地址，`ss -tuln` 对应 `netstat -tuln` 查看 TCP/UDP 端口。`netstat -r` 查看路由、`netstat -i` 查看接口统计、`netstat -s` 查看协议统计；`netstat -p` 显示进程时可能需要提升权限。`netstat` 输出中的 `Recv-Q`、`Send-Q` 含义随套接字状态变化，不能统一理解为累计收发字节数。

## 5. 文件系统目录速览

Linux 的目录布局可用文件系统层次标准（FHS）理解，但具体发行版可能采用 `/usr` 合并布局，使 `/bin`、`/sbin` 等成为指向 `/usr` 下对应目录的符号链接。以下是常见目录的用途，不应据此假定每台机器都具有相同布局。

| 目录 | 常见用途 |
| --- | --- |
| `/` | 整个目录树的起点 |
| `/bin`、`/sbin` | 传统布局中的基本命令和系统管理命令；合并布局中可能是符号链接 |
| `/usr/bin`、`/usr/sbin` | 大部分用户命令和系统管理命令 |
| `/usr/lib`、`/usr/share` | 库文件与架构无关的共享数据 |
| `/usr/local` | 管理员在本机安装的软件与数据 |
| `/etc` | 系统及服务配置，例如 `/etc/passwd`、`/etc/fstab` |
| `/home`、`/root` | 普通用户与 root 用户的主目录 |
| `/var` | 会变化的数据，例如 `/var/log` 中的日志 |
| `/run` | 当前运行期的状态数据，例如 PID 文件和套接字；重启后不应依赖其中的旧内容 |
| `/tmp` | 临时文件；清理时机由系统策略决定 |
| `/dev` | 设备节点，例如 `/dev/tty` |
| `/proc`、`/sys` | 内核提供的虚拟文件系统，分别呈现进程/内核信息和设备/内核对象信息 |
| `/boot` | 启动相关文件，具体内容随启动方案而异 |
| `/media`、`/mnt` | 可移动媒体挂载点与临时手动挂载点 |
| `/opt` | 附加软件包 |

## 参考资料

- [GNU `chmod` 手册](https://man7.org/linux/man-pages/man1/chmod.1.html)、[`umask` 手册](https://man7.org/linux/man-pages/man2/umask.2.html)
- [`uptime` 手册](https://man7.org/linux/man-pages/man1/uptime.1.html)、[`df` 手册](https://man7.org/linux/man-pages/man1/df.1.html)
- [`ss` 手册](https://man7.org/linux/man-pages/man8/ss.8.html)、[`netstat` 手册](https://man7.org/linux/man-pages/man8/netstat.8.html)
- [文件系统层次标准（FHS）](https://specifications.freedesktop.org/fhs/latest/)、[Ubuntu 防火墙文档](https://documentation.ubuntu.com/server/how-to/security/firewalls/index.html)
