import time
import multiprocessing

def file_thread():
    i = 0
    while True:
        with open("output.txt", "a") as f:
            f.write(f"Currently on number {i} IN FILE\n")
        i += 1

        time.sleep(1)

multiprocessing.Process(target=file_thread).start()

i = 0
while True:
    print(f"Currently on number {i}")
    i += 1


    time.sleep(1)

    with open("output.txt", "r") as f:
        lines = f.readlines()
        print(lines[-1])

