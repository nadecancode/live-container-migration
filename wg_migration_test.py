


# CLI parsing too much work, we take IPs as variables
# I run this from my server since ssh from ucsd on ucsd wifi is slow
ND_0 = "54.191.27.210"
ND_1 = "54.218.14.120"
ND_2 = "52.26.235.11"
ND_3 = "34.218.249.146"

# Start server on node 1, 2

# Start iperf container on node 0
# podman run -dt --runtime=runc --name iperf3 -p 5201:5201 --replace --privileged  docker.io/networkstatic/iperf3 -s -J


# Start iperf on node 3 connecting to node 0



# Wait 20 seconds, migrate from node 0 to node 1


# Wait 20 seconds, migrate from node 1 to node 2


# Finish up, then clean up (remove containers on all nodes)


# Output iperf results to json
