# "apt-get update && apt-get install curl -y && curl -s https://raw.githubusercontent.com/ITZVGcGPmO/kris-harbour-turbine/master/installscripts/RaspbianInstall.sh | bash -s"
apt-get update
apt upgrade -y
apt install python3.6 git -y
cd /usr/share
git clone https://github.com/ITZVGcGPmO/kris-harbour-turbine
cd kris-harbour-turbine
rm -rf .git
rm -rf .gitignore
cat > /lib/systemd/system/khturbine.service <<EOF
[Unit]
Description=Kris harbour turbine watcher
After=multi-user.target[Service]
Type=idle
ExecStart=/usr/bin/python3.6 /usr/share/kris-harbour-turbine/adjuster .py[Install]
WantedBy=multi-user.target
EOF
chmod 644 /lib/systemd/system/khturbine.service
systemctl daemon-reload
systemctl enable khturbine.service
systemctl status khturbine.service