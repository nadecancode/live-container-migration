import subprocess


def run_ssh_command(ip, command):
    # use popen for async
    return subprocess.Popen(f"ssh root@{ip} {command}", shell=True, stdout=subprocess.PIPE, text=True)


# CLI parsing too much work, we take IPs as variables
# I run this from my server since ssh from ucsd on ucsd wifi is slow
ND_0 = "54.191.27.210"
ND_1 = "54.218.14.120"
ND_2 = "52.26.235.11"
ND_3 = "34.218.249.146"

# Start server on node 1, 2
# poetry run python agent-server/main.py
run_ssh_command(ND_1, "'cd live-container-migration && poetry run python agent-server/main.py'")
run_ssh_command(ND_2, "'cd live-container-migration && poetry run python agent-server/main.py'")

# Start iperf container on node 0
# podman run -dt --runtime=runc --name iperf3 -p 5201:5201 --replace --privileged  docker.io/networkstatic/iperf3 -s -J
run_ssh_command(ND_0, "podman run -dt --runtime=runc --name iperf3 -p 5201:5201 --replace --privileged  docker.io/networkstatic/iperf3 -s -J")


# Start iperf on node 3 connecting to node 0
# iperf3 -J --bidir -t 60 -c IP -p 5201
output = run_ssh_command(ND_3, f"iperf3 -J --bidir -t 60 -c {ND_0} -p 5201")


# Wait 20 seconds, migrate from node 0 to node 1
# poetry run python agent-client/main.py --use-cli-args --host ND_1 --port 50051 --container_num 0


# Wait 20 seconds, migrate from node 1 to node 2
# poetry run python agent-client/main.py --use-cli-args --host ND_2 --port 50051 --container_num 0


# Wait another 20 seconds, then wait for iperf to finish up to 30s; if its not done, it's deadlocked
# I noticed this failure mode at CAIDA, I think if iperf gets packet flow interrupted it just... won't die
# So kill iperf after the 30 seconds



# Finish up, then clean up (remove containers on all nodes)
# podman stop iperf3
# podman rm iperf3


# Output iperf results to json
