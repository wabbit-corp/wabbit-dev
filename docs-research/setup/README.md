# Generating a new key pair
```bash
ssh-keygen -a 500 -o -t rsa -b 4096 -C "alex.knvl@gmail.com"
eval "$(ssh-agent -s)"
ssh-add /path/to/id_pub
```

# Adding a new user
```bash
adduser user
usermod -aG sudo user
su - user
mkdir ~/.ssh
chmod 700 ~/.ssh
# Copy public key here.
vim ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
exit
```

# Limit `su` access to administrators only
```bash
dpkg-statoverride --update --add root sudo 4750 /bin/su
```

# Configuring SSH
Change both `PermitRootLogin` and `PasswordAuthentication` to `no` in `/etc/ssh/sshd_config`. Change `Port` from 22 to another port of your choice.

Reload SSH by doing
```bash
service ssh reload
```

# Improve IP security
Add the following lines to /etc/sysctl.d/10-network-security.conf to improve IP security:
```
# Ignore ICMP broadcast requests
net.ipv4.icmp_echo_ignore_broadcasts = 1

# Disable source packet routing
net.ipv4.conf.all.accept_source_route = 0
net.ipv6.conf.all.accept_source_route = 0 
net.ipv4.conf.default.accept_source_route = 0
net.ipv6.conf.default.accept_source_route = 0

# Ignore send redirects
net.ipv4.conf.all.send_redirects = 0
net.ipv4.conf.default.send_redirects = 0

# Block SYN attacks
net.ipv4.tcp_max_syn_backlog = 2048
net.ipv4.tcp_synack_retries = 2
net.ipv4.tcp_syn_retries = 5

# Log Martians
net.ipv4.conf.all.log_martians = 1
net.ipv4.icmp_ignore_bogus_error_responses = 1

# Ignore ICMP redirects
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
net.ipv4.conf.default.accept_redirects = 0 
net.ipv6.conf.default.accept_redirects = 0

# Ignore Directed pings
net.ipv4.icmp_echo_ignore_all = 1
```

Load the new rules:
```bash
sudo service procps start
```

# Firewall
```bash
sudo apt-get install ufw
sudo ufw allow <ssh-port>/tcp
sudo ufw enable
sudo ufw status
```

# Install rootkit hunters
```bash
sudo apt-get install rkhunter chkrootkit
```

1. In /etc/chkrootkit.conf, change `RUN_DAILY` to "true" so that it runs regularly, and change "-q" to "" otherwise the output doesn’t make much sense.
2. In /etc/default/rkhunter, change `CRON_DAILY_RUN` and `CRON_DB_UPDATE` to "true" so it runs regularly.

# Install logwatch
```bash
apt-get install logwatch
mv /etc/cron.daily/00logwatch /etc/cron.weekly/
```

Make it show output from the last week by editing `/etc/cron.weekly/00logwatch` and adding `--range 'between -7 days and -1 days'` to the end of the `/usr/sbin/logwatch` command.

