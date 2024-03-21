# Live Container Migration

This repository contains the code for a live container migration system implemented using Python 3. This was done as part of our final project for CSE 291 (Cloud Computing & Virtualization) taught by Yiying Zhang (https://cseweb.ucsd.edu/~yiying/cse291-winter24/). 

Once we have permission to do so, you'll be able to find a (revised) version of the final report here.

## Overview

The live container migration project provides a means to transfer running containers between servers without significant service disruption. Specifically, we focused on migrating containers with active network connections, without disrupting those connections. We currently fully support TCP connection migration, and UDP migration should work at low packets per second or throughput. We used WireGuard for the network tunneling, CRIU for the checkpoint/restore functionality, and Podman for container management. We also extensively used firewall rules and manual conntrack editing to get connections to be migrated.

Note that once you migrate the new container successfully, the old container will be stopped and deleted. You also won't be able to make new connections to the migrated container from the old host, you'll have to connect to the host it was migrated to. If you want to change this behavior, you can do so by uncommenting the DNAT rules in the client agent. However, you'll need to make sure to clean those up when you're done.


## Components

- `agent-client`: Contains the client-side agent that initiates and coordinates the migration process.
- `agent-server`: Houses the server-side agent that accepts and completes the migration request.
- `container/example`: Some of the containers we used for testing the migration process. net-* is incomplete, as we used docker.io/cjimti/go-echo and docker.io/networkstatic/iperf3 for our network tests instead.
- `common/net.py`: Core logic for network connection migration handling.

## Prerequisites

- Linux environment with kernel support for CRIU and WireGuard.
- A reasonably up to date Linux distribution (we used Arch Linux)
- WireGuard installed on both source and destination servers.
- Podman with CRIU plugin for checkpoint/restore functionality.
- Python 3.x.

Here is the list of packages we used on Arch Linux:
```sh
pacman -S wireguard-tools tcpdump base-devel neovim kitty linux podman inetutils conntrack-tools iproute2 runc python-poetry git openssh
```

This list may not be exhaustive, so make sure to install any missing packages. For other distributions, the package names may vary.

## Installation

1. Clone this repository to both source and destination machines:
    ```sh
    git clone https://github.com/nadecancode/live-container-migration.git
    ```
2. Navigate to the cloned directory:
    ```sh
    cd live-container-migration
    ```
3. Install required Python packages using poetry:
    ```sh
    poetry install
    ```
4. Activate the poetry shell: 
    ```sh
    poetry install
    ```

## Usage

1. Start the server agent on the destination machine:
    ```sh
    python agent-server/main.py
    ```
2. Execute the client agent on the source machine, specifying the container ID and destination:
    ```sh
    python agent-client/main.py
    ```
   If you want to automate this, look at the `wg_migration_test.py` script to see how to bypass the interactive mode.


## Testing

- `wg_migration_test.py`: Used to automatically test the migration process with a running iperf3 test. If you want to use it, make sure to change the IPs to the one you'll be using. If the resulting json has "bad" in it, it took more than 20 seconds to run the first migration. If it has "notbad", then it completed in less than 20 seconds.

## Results

Since the graphs in the final report are very small, we've included them here for better visibility.

### TCP graphs

![figure-7.png](graphs%2Ffigure-7.png)
![figure-8.png](graphs%2Ffigure-8.png)

### UDP Graphs

![figure-6.png](graphs%2Ffigure-6.png)
![jitter.png](graphs%2Fjitter.png)
![udppps.png](graphs%2Fudppps.png)

When migrating for the first time (cold migration), it will take much longer due to caching. If you need to do this with low downtime or quickly, migrate another instance of the same container image first (doesn't need to be the same container).