import time
import multiprocessing

def file_thread():
    i = 0
    f = open("output.txt", "a")
    while True:
        f.write(f"Currently on number {i} IN FILE\n")
        with open("output_c.txt", "a") as consistent:
            consistent.write(f"CONSISTENTLY on number {i}\n")
        i += 1

        try:
            with open("kill.txt", "r") as kill:
                lines = kill.readlines()
                if "a" in lines[-1]:
                    f.close()
                    break
        except:
            pass

        time.sleep(1)

multiprocessing.Process(target=file_thread).start()

i = 0
while True:
    print(f"Currently on number {i}")
    i += 1


    time.sleep(1)

    try:
        with open("output.txt", "r") as f:
            lines = f.readlines()
            print(lines[-1])
    except:
        pass
    with open("output_c.txt", "r") as f:
        lines = f.readlines()
        print(lines[-1])



