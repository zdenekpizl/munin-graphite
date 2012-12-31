#!/usr/bin/python
"""Gather Munin statistics and deliver to Carbon for Graphite display."""

#from multiprocessing import Pool
import argparse
import logging
import pickle
import re
import socket
import struct
import sys
import time

LOGGING_FORMAT = "%(asctime)s : %(levelname)s : %(message)s"
HOSTLIST = ["localhost"]
RE_LEFTRIGHT = re.compile(r"^(?P<left>\S+)\s+(?P<right>\S+)$")

class Munin():
    """Munin host object with querying getter functions."""
    def __init__(self, hostname="localhost", port=4949, args=None):
        self.hostname = hostname
        self.port = port
        self.args = args

    def connect(self):
        """Initial connection to Munin host."""
        try:
            self._sock = socket.create_connection((self.hostname, self.port),
                                                  10)
        except socket.error:
            logging.exception("Unable to connect to Munin host %s, port: %s",
                              self.hostname, self.port)
            sys.exit(1)

        self._conn = self._sock.makefile()
        self.hello_string = self._readline()

    def close_connection(self):
        """Close connection to Munin host."""
        self._sock.close()

    def _readline(self):
        """Read one line from Munin output, stripping leading/trailing chars."""
        return self._conn.readline().strip()

    def _iterline(self):
        """Iterator over Munin output."""
        while True:
            current_line = self._readline()
            logging.debug("Iterating over line: %s", current_line)
            if not current_line:
                break
            if current_line.startswith("#"):
                continue
            if current_line == ".":
                break
            yield current_line

    def fetch(self, plugin):
        """Fetch plugin's data fields from Munin."""
        self._sock.sendall("fetch %s\n" % plugin)
        response = {}
        for current_line in self._iterline():
            # Some munin plugins have more than one space between key and value.
            full_key_name, key_value = RE_LEFTRIGHT.search(current_line).group(1, 2)
            key_name = full_key_name.split(".")[0]
            response[key_name] = key_value

        return response

    def list_plugins(self):
        """Return a list of Munin plugins configured on a node. """
        self._sock.sendall("list\n")
        plugin_list = self._readline().split(" ")
        return plugin_list

    def get_config(self, plugin):
        """Get config values for Munin plugin."""
        self._sock.sendall("config %s\n" % plugin)
        response = {}

        for current_line in self._iterline():
            key_name, key_value = current_line.split(" ", 1)
            if "." in key_name:
                # Some keys have periods in them.
                # If so, make their own nested dictionary.
                key_root, key_leaf = key_name.split(".", 1)
                if key_root not in response:
                    response[key_root] = {}
                response[key_root][key_leaf] = key_value
            else:
                response[key_name] = key_value

        return response


    def process_host_stats(self):
        """Process Munin node data, potentially sending to Carbon."""
        plugins = self.list_plugins()
        logging.debug("Plugin List: %s", plugins)
        timestamp = int(time.time())

        for current_plugin in plugins:
            logging.info("Fetching plugin: %s (Host: %s)",
                         current_plugin, self.hostname)

            plugin_config = self.get_config(current_plugin)
            logging.debug("Plugin Config: %s", plugin_config)

            plugin_data = self.fetch(current_plugin)
            logging.debug("Plugin Data: %s", plugin_data)
            if self.args.carbon:
                self.send_to_carbon(timestamp, current_plugin, plugin_config, plugin_data)

    def send_to_carbon(self, timestamp, plugin_name, plugin_config, plugin_data):
        """Send plugin data to Carbon over Pickle format."""
        carbon_host, carbon_port = self.args.carbon.split(":")
        data_list = []
        logging.info("Creating metrics for plugin %s, timestamp: %d",
                     plugin_name, timestamp)
        short_hostname = self.hostname.split(".")[0]
        for data_key in plugin_data:
            plugin_category = plugin_config["graph_category"]
            metric = "servers.%s.%s.%s.%s" % (short_hostname, plugin_category, plugin_name, data_key)
            value = plugin_data[data_key]
            logging.debug("Creating metric %s, value: %s", metric, value)
            data_list.append((metric, (timestamp, value)))

        payload = pickle.dumps(data_list)
        header = struct.pack("!L", len(payload))
        message = header + payload
        if self.args.noop:
            logging.info("NOOP: Not sending data to Carbon")
            return

        logging.info("Sending plugin %s data to Carbon for host %s.",
                     plugin_name, self.hostname)
        carbon_sock = socket.create_connection((carbon_host, carbon_port), 10)
        carbon_sock.sendall(message)
        carbon_sock.close()
        logging.info("Finished sending plugin %s data to Carbon for host %s.",
                     plugin_name, self.hostname)

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Send Munin statistics to Graphite.")
    parser.add_argument("--carbon",
                        action="store",
                        help="Carbon hostport (ex: localhost:2003).")
    parser.add_argument("-n", "--noop",
                        action="store_true",
                        help="Don't actually send Munin data to Carbon.")
    parser.add_argument("-v", "--verbose",
                        choices=[1, 2, 3],
                        default=2,
                        type=int,
                        help="Verbosity level. 1:ERROR, 2:INFO/Default, 3:DEBUG.")

    args = parser.parse_args()
    return args

if __name__ == '__main__':
    args = parse_args()
    if args.verbose == 3:
        LOGGING_LEVEL = logging.DEBUG
    elif args.verbose == 1:
        LOGGING_LEVEL = logging.ERROR
    else:
        LOGGING_LEVEL = logging.INFO

    logging.basicConfig(format=LOGGING_FORMAT, level=LOGGING_LEVEL)
    while True:
        for current_host in HOSTLIST:
            start_time = time.time()
            logging.info("Querying host: %s", current_host)
            munin_host = Munin(hostname=current_host, args=args)
            munin_host.connect()
            munin_host.process_host_stats()
            munin_host.close_connection()
            end_time = time.time()
            elapsed_time = end_time - start_time
            logging.info("Finished querying host %s (Execution Time: %.2f sec)",
                         current_host, elapsed_time)
        time.sleep(60)
