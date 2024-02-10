sudo apt-get update
sudo apt-get -y install podman runc criu
sudo systemctl start podman.socket
sudo systemctl enable podman.socket

# change oci runtime to runc - https://serverfault.com/questions/989509/how-can-i-change-the-oci-runtime-in-podman
