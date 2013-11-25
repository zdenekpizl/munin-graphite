#!/usr/bin/python
"""Gather Munin statistics and deliver to Carbon for Graphite display."""

import argparse
import logging
import pickle
import re
import socket
import struct
import sys
import time

LOGGING_FORMAT = "%(asctime)s:%(levelname)s:%(message)s"
RE_LEFTRIGHT = re.compile(r"^(?P<left>\S+)\s+(?P<right>\S+)$")

## TODO: Catch keyboard interrupt properly and die when requested

class Munin():
    """Munin host object with querying getter functions."""
    def __init__(self, hostname, port=4949, args=None):
        self.hostname = hostname
        self.port = port
        self.args = args
        self.displayname = self.hostname.split(".")[0]

        if self.args.displayname:
            self.displayname = self.args.displayname

    def go(self):
        """Bootstrap method to start processing hosts's Munin stats."""
        while True:
            self.connect()
            self.process_host_stats()
            time.sleep(self.args.interval)

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
        start_timestamp = time.time()
        logging.info("Querying host %s", self.hostname)
        plugins = self.list_plugins()
        logging.debug("Plugin List: %s", plugins)
        epoch_timestamp = int(start_timestamp)

        for current_plugin in plugins:
            logging.info("Fetching plugin: %s (Host: %s)",
                         current_plugin, self.hostname)

            plugin_config = self.get_config(current_plugin)
            logging.debug("Plugin Config: %s", plugin_config)

            plugin_data = self.fetch(current_plugin)
            logging.debug("Plugin Data: %s", plugin_data)
            if self.args.carbon:
                self.send_to_carbon(epoch_timestamp,
                                    current_plugin,
                                    plugin_config,
                                    plugin_data)
        end_timestamp = time.time() - start_timestamp
        self.close_connection()
        logging.info("Finished querying host %s (Execution Time: %.2f sec).",
                     self.hostname, end_timestamp)


    def send_to_carbon(self, timestamp, plugin_name, plugin_config, plugin_data):
        """Send plugin data to Carbon over Pickle format."""
        carbon_host, carbon_port = self.args.carbon.split(":")
        if self.args.noprefix:
            prefix = ''
        else:
            prefix = "%s." % self.args.prefix
        data_list = []
        logging.info("Creating metric for plugin %s, timestamp: %d",
                     plugin_name, timestamp)

        for data_key in plugin_data:
            plugin_category = plugin_config["graph_category"]
            metric = "%s%s.%s.%s.%s" % (prefix, self.displayname, plugin_category, plugin_name, data_key)
            value = plugin_data[data_key]
            logging.debug("Creating metric %s, value: %s", metric, value)
            data_list.append((metric, (timestamp, value)))

        if self.args.noop:
            logging.info("NOOP: Not sending data to Carbon")
            return

        logging.info("Sending plugin %s data to Carbon for host %s.",
                     plugin_name, self.hostname)
        payload = pickle.dumps(data_list)
        header = struct.pack("!L", len(payload))
        message = header + payload
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
                        help="Carbon host and Pickle port (ex: localhost:2004).")
    parser.add_argument("--host",
                        action="store",
                        default="localhost",
                        help="Munin host to query for stats. Default: %(default)s")
    parser.add_argument("--displayname",
                        default=False,
                        help="If defined, use this as the name to store metrics in Graphite instead of the Munin hostname.")
    parser.add_argument("--interval",
                        type=int,
                        default=60,
                        help="Interval (seconds) between polling Munin host for statistics. Default: %(default)s")
    parser.add_argument("--noop",
                        action="store_true",
                        help="Don't actually send Munin data to Carbon. Default: %(default)s")
    parser.add_argument("--noprefix",
                        action="store_true",
                        default=False,
                        help="Do not use a prefix on graphite target's name. Default: %(default)s")
    parser.add_argument("--prefix",
                        action="store",
                        default="servers",
                        help="Prefix used on graphite target's name. Default: %(default)s")
    parser.add_argument("--verbose","-v",
                        choices=[1, 2, 3],
                        default=2,
                        type=int,
                        help="Verbosity level. 1:ERROR, 2:INFO, 3:DEBUG. Default: %(default)d")

    args = parser.parse_args()
    return args

def main():
    args = parse_args()
    if args.verbose == 1:
        LOGGING_LEVEL = logging.ERROR
    elif args.verbose == 3:
        LOGGING_LEVEL = logging.DEBUG
    else:
        LOGGING_LEVEL = logging.INFO

    logging.basicConfig(format=LOGGING_FORMAT, level=LOGGING_LEVEL)
    munin = Munin(hostname=args.host, args=args)
    munin.go()

if __name__ == '__main__':
    main()
