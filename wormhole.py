import requests
import threading
from queue import Queue
import urllib3
from pyuseragents import random as random_useragent

urllib3.disable_warnings()

bad_addresses_file = "bad-addresses.txt"
BLOCKCHAINS = {
            "sol": 1,
            "eth": 2,
            "sui": 21,
            "aptos": 22,
            "inj": 19,
            "terra": 3,
            "algorand": 8,
            "osmosis": 20,
        }

def load_proxies(fp: str = "proxies.txt"):
    proxies = []
    with open(file=fp, mode="r", encoding="utf-8") as File:
        lines = File.read().split("\n")
    for line in lines:
        try:
            proxies.append(f"http://{line}")
        except ValueError:
            pass

    if proxies.__len__() < 1:
        raise Exception("can't load empty proxies file!")

    print("{} proxies loaded successfully!\n".format(proxies.__len__()))

    return proxies

class PrintThread(threading.Thread):
    def __init__(self, queue, file):
        threading.Thread.__init__(self)
        self.queue = queue
        self.file = file

    def printfiles(self, filename: str, text: str):
        with open(filename, "a", encoding="utf-8") as ff:
            ff.write(text + '\n')

    def run(self):
        while True:
            addr = self.queue.get()
            self.printfiles(self.file, addr)
            self.queue.task_done()

class ProcessThread(threading.Thread):
    def __init__(self, in_queue, out_queue, bad_queue, blockchain):
        threading.Thread.__init__(self)
        self.in_queue = in_queue
        self.out_queue = out_queue
        self.bad_queue = bad_queue
        self.blockchain = BLOCKCHAINS[blockchain]

    def run(self):
        while True:
            addr = self.in_queue.get()
            res, bad = self.get_allocation(addr)
            if res != "":
                self.out_queue.put(res)
            elif bad != "":
                self.bad_queue.put(bad)

            global completed_addresses, total_addresses
            completed_addresses += 1
            print(f"Completed {completed_addresses} out of {total_addresses}, Remaining: {total_addresses - completed_addresses} addresses\n")
            
            self.in_queue.task_done()

    def get_allocation(self, address: str):
        t = 0
        while True:
            try:
                with proxy_pool_lock:
                    if proxy_pool:
                        selected_proxy = proxy_pool.pop(0)
                    else:
                        print("Proxy pool is empty\n")
                        continue

                sess = requests.session()
                sess.proxies = {'all': selected_proxy}
                sess.headers = {
                    'User-Agent': random_useragent(),
                    'Accept-Encoding': 'gzip, deflate',
                    'Accept': '*/*',
                    'Connection': 'keep-alive',
                }
                sess.verify = True

                if self.blockchain == 2: address = address.lower()

                response = sess.get(f"https://prod-flat-files-min.wormhole.com/{address}_{self.blockchain}.json")
                if response.status_code == 200:
                    if response.json():
                        if response.json()['amount'] != 0:
                            return f"{address}: {response.json()['amount'] * 1e-9}", ""
                
                if response.status_code == 404 or response.status_code == 200:
                    return "", ""
                
                t += 1
                if t == 4:
                    print(f"bad address {address}: status {response.status_code}")
                    return "", f"{address}: status {response.status_code}"
            except Exception as e:
                print(f'Error {selected_proxy}: {e}. Повтор запроса с другим прокси..\n')
                pass

            finally:
                with proxy_pool_lock:
                    proxy_pool.append(selected_proxy)

completed_addresses = 0

proxy_pool = load_proxies(input('Path to proxies: '))
# proxy_pool = load_proxies('prx.txt')
proxy_pool_lock = threading.Lock()

file = input('Path to file with adr: ')
# file = 'addresses.txt'

with open(file, encoding="utf-8") as f:
    addresses = f.read().splitlines()
total_addresses = len(addresses)
print(f'{total_addresses} addresses loaded sucessfully!\n')

path_to_save = input('Path to save: ')
# path_to_save = 'sac.txt'

ch = input(f'\nSelect chain {list(BLOCKCHAINS.keys())}: ')
while ch not in BLOCKCHAINS.keys():
    print(f'\nChain must be in {list(BLOCKCHAINS.keys())}\n')
    ch = input(f'Select chain {list(BLOCKCHAINS.keys())}: ')

threads = int(input('\nMax threads (должно быть не больше количества прокси): '))
# threads = 1

print('\nstarted\n')

pathqueue = Queue()
resultqueue = Queue()
badqueue = Queue()

for i in range(0, threads):
    t = ProcessThread(pathqueue, resultqueue, "", ch)
    t.daemon = True
    t.start()

t = PrintThread(resultqueue, path_to_save)
t.daemon = True
t.start()

b = PrintThread(badqueue, bad_addresses_file)
b.daemon = True
b.start()

for address in addresses:
    pathqueue.put(address.strip())

pathqueue.join()
resultqueue.join()
badqueue.join()

print("cancel")