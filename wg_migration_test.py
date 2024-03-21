import datetime
import subprocess
import threading
import time

# CLI parsing too much work, we take IPs as variables
# I run this from a remote server since ssh from ucsd on ucsd wifi is slow
# First run after a reboot will be useless, since some caching needs to happen. This shouldn't cause downtime.
ND_0 = "44.234.245.19"
ND_1 = "52.10.244.151"
ND_2 = "35.161.225.2"
ND_3 = "34.209.121.58"


def run_ssh_command(ip, command):
    print(f"Running {command} on {ip}")
    if ip == ND_3:
        return subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, text=True)
    # use popen for async
    return subprocess.Popen(f"ssh root@{ip} {command}", shell=True, stdout=subprocess.PIPE, text=True)


# Start server on node 1, 2
# poetry run python agent-server/main.py
run_ssh_command(ND_1, "'cd live-container-migration/agent-server && poetry run python main.py'")
run_ssh_command(ND_2, "'cd live-container-migration/agent-server && poetry run python main.py'")

print("Servers started")

# Start iperf container on node 0
# podman run -dt --runtime=runc --name iperf3 -p 5201:5201 --replace --privileged  docker.io/networkstatic/iperf3 -s -J
run_ssh_command(ND_0,
                "podman run -dt --runtime=runc --name iperf3 -p 5201:5201/tcp -p 5201:5201/udp --replace --privileged  docker.io/networkstatic/iperf3 -s -J").wait()

print("Iperf container started")

time.sleep(5)

# Start iperf on node 3 connecting to node 0
# iperf3 -J --bidir -t 80 -c IP -p 5201
# leave 20 extra seconds for various migration things
output = run_ssh_command(ND_3, f"iperf3 -J --bidir -t 80 -c {ND_0} -p 5201 --get-server-output")

print("Iperf started")

# Wait 20 seconds, migrate from node 0 to node 1
# poetry run python main.py --use-cli-args --host ND_1 --port 50051 --container_num 0
m1_finished = threading.Event()
bad_test = threading.Event()


def migrate(from_, to, time_, check_finished):
    time.sleep(time_)
    if check_finished:
        if not m1_finished.is_set():
            bad_test.set()
        m1_finished.wait()
    run_ssh_command(from_,
                    f"'cd live-container-migration/agent-client && poetry run python main.py --use-cli-args --host {to} --port 50051 --container_num 0'").wait()
    m1_finished.set()


t1 = threading.Thread(target=migrate, args=(ND_0, ND_1, 20, False))

# Wait 20 seconds, migrate from node 1 to node 2; use threading to try to be exact, but also wait for first migration to finish
# poetry run python agent-client/main.py --use-cli-args --host ND_2 --port 50051 --container_num 0

t2 = threading.Thread(target=migrate, args=(ND_1, ND_2, 40, True))

t1.start()
t2.start()

print("Threads started")

# Wait another 20 seconds, then wait for iperf to finish up to 30s; if its not done, it's deadlocked
# I noticed this failure mode at CAIDA, I think if iperf gets packet flow interrupted it just... won't die
# So kill iperf after the 30 seconds
time.sleep(60)
t1.join(20)
t2.join(20)
print("Threads joined")
run_ssh_command(ND_1, "pkill -9 python")
run_ssh_command(ND_2, "pkill -9 python")
try:
    out, err = output.communicate(timeout=30)
except subprocess.TimeoutExpired:
    output.kill()
    run_ssh_command(ND_3, "pkill -9 iperf3").wait()
    out, err = output.communicate()

print("Iperf finished")

# Finish up, then clean up (remove containers on all nodes)
# podman stop iperf3
# podman rm iperf3
n0 = run_ssh_command(ND_0, "podman stop iperf3")
n1 = run_ssh_command(ND_1, "podman stop iperf3")
n2 = run_ssh_command(ND_2, "podman stop iperf3")
n0.wait()
n1.wait()
n2.wait()
n0 = run_ssh_command(ND_0, "podman rm iperf3")
n1 = run_ssh_command(ND_1, "podman rm iperf3")
n2 = run_ssh_command(ND_2, "podman rm iperf3")
n0.wait()
n1.wait()
n2.wait()

print("Cleaned up iperf containers")

# Kill server on all nodes
n0 = run_ssh_command(ND_0, "pkill -9 python")
n1 = run_ssh_command(ND_1, "pkill -9 python")
n2 = run_ssh_command(ND_2, "pkill -9 python")
n0.wait()
n1.wait()
n2.wait()

print("Killed servers")

bad = "notbad"
if bad_test.is_set():
    bad = "bad"

now = datetime.datetime.now().strftime("%d-%H-%M")

# Output iperf results to json
with open(f"iperf_{now}_{bad}.json", "w") as f:
    f.write(out)

print("Done")