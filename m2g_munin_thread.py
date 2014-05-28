#!/usr/bin/python
"""Gather Munin statistics and deliver to Carbon for Graphite display."""

import argparse
import pickle
import re
import socket
import struct
import sys
import time
import logging
import threading

RE_LEFTRIGHT = re.compile(r"^(?P<left>\S+)\s+(?P<right>\S+)$")
RE_MUNIN_NODE_NAME = re.compile(r"^# munin node at\s+(?P<nodename>\S+)$")


class Munin():
    """Munin host object with querying getter functions."""

    def __init__(self, hostname, logger=None, port=4949, args=None):

        self.hostname = None
        self.remotenode = None
        self._sock = None
        self._conn = None
        self._carbon_sock = None
        self.hello_string = None
        self.reload_plugins = True
        self.shutdown = False
        self.plugins = {}
        self.plugins_config = {}
        self.port = port
        self.args = args

        if ':' in hostname:
            self.hostname, self.remotenode = hostname.split(":", 1)
        else:
            self.hostname = hostname

        if self.args.displayname:
            self.displayname = self.args.displayname.split(".")[0]
        else:
            self.displayname = self.hostname.split(".")[0]

        if logger:
            self.logger = logger
        else:
            # if we have not provided a logger, let's create a very basic one
            self.logger = logging.getLogger()

    def set_shutdown(self,newstatus):
        """Updating shutdown status from connection hello string."""
        self.shutdown = newstatus

    def set_reload_plugins(self,newstatus):
        """Updating shutdown status from connection hello string."""
        self.reload_plugins = newstatus

    def go(self):
        """Bootstrap method to start processing hosts's Munin stats."""
        self.connect()
        self.update_hostname()
        processing_time = self.process_host_stats()
        interval = int(self.args.interval)

        while True and interval != 0 and not self.shutdown:
            sleep_time = max(interval - processing_time, 0)
            time.sleep(sleep_time)
            self.connect()
            processing_time = self.process_host_stats()

    def update_hostname(self):
        """Updating hostname from connection hello string."""
        if self.args.displayname:
            return
        try:
            node_name = RE_MUNIN_NODE_NAME.search(self.hello_string).group(1)
            self.displayname = node_name.split(".")[0]
        except AttributeError:
            self.logger.info("Thread %s: Unable to obtain munin node name from: %s",
                        self.hostname, self.hello_string)
            return

    def connect(self):
        """Initial connection to Munin host."""
        try:
            self._sock = socket.create_connection((self.hostname, self.port), 10)
        except socket.error:
            self.logger.exception("Thread %s: Unable to connect to Munin host %s, port: %s",
                             self.hostname, self.hostname, self.port)
            sys.exit(1)

        try:
            self._conn = self._sock.makefile()
            self.hello_string = self._readline()
        except socket.error:
            self.logger.exception("Thread %s: Unable to communicate to Munin host %s, port: %s",
                             self.hostname, self.hostname, self.port)

        try:
            if self.args.carbon:
                self.connect_carbon()
        except AttributeError as e:
            self.logger.debug("Thread %s: connection to Carbon not defined, that is not necessary an error")


    def connect_carbon(self):
        carbon_host, carbon_port = self.args.carbon.split(":")
        try:
            self._carbon_sock = socket.create_connection((carbon_host, carbon_port), 10)
        except socket.error:
            self.logger.exception("Thread %s: Unable to connect to Carbon on host %s, port: %s",
                             self.hostname, carbon_host, carbon_port)
            sys.exit(1)

    def close_connection(self):
        """Close connection to Munin host."""
        self._sock.close()

    def close_carbon_connection(self):
        """Close connection to Carbon host."""
        if self._carbon_sock:
            self._carbon_sock.close()

    def _readline(self):
        """Read one line from Munin output, stripping leading/trailing chars."""
        return self._conn.readline().strip()

    def _iterline(self):
        """Iterator over Munin output."""
        while True:
            current_line = self._readline()
            self.logger.debug("Thread %s: Iterating over line: %s", self.hostname, current_line)
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
        response = {plugin: {}}
        multigraph = plugin
        multigraph_prefix = ""
        for current_line in self._iterline():
            if current_line.startswith("multigraph "):
                multigraph = current_line[11:]
                multigraph_prefix = multigraph.rstrip(".") + "."
                response[multigraph] = {}
                continue
                # Some munin plugins have more than one space between key and value.
            try:
                full_key_name, key_value = RE_LEFTRIGHT.search(current_line).group(1, 2)
                key_name = multigraph_prefix + full_key_name.split(".")[0]
                response[multigraph][key_name] = key_value
                print "***************************** Response: %r" % response
            except (KeyError, AttributeError):
                self.logger.info("Thread %s: Plugin %s returned invalid data [%s] for host"
                            " %s\n", self.hostname, plugin, current_line, self.hostname)

        return response

    def list_plugins(self):
        """Return a list of Munin plugins configured on a node. """
        self._sock.sendall("cap multigraph\n")
        self._readline()  # ignore response

        if self.remotenode:
            self.logger.info("Thread %s: Asking for plugin list for remote node %s", self.hostname, self.remotenode)
            self._sock.sendall("list %s\n" % self.remotenode)
        else:
            self.logger.info("Thread %s: Asking for plugin list for local node %s", self.hostname, self.hostname)
            self._sock.sendall("list\n")

        plugin_list = self._readline().split(" ")
        if self.args.filter:
            try:
                filteredlist = [plugin for plugin in plugin_list if re.search(self.args.filter, plugin, re.IGNORECASE)]
                plugin_list = filteredlist
            except re.error:
                self.logger.info("Thread %s: Filter regexp for plugin list is not valid: %s" % self.args.filter)
            # if there is no filter or we have got an re.error, simply return full list
        result_list = []
        for plugin in plugin_list:
            if len(plugin.strip()) > 0:
                result_list.append(plugin)
        return result_list

    def get_config(self, plugin):
        """Get config values for Munin plugin."""
        self._sock.sendall("config %s\n" % plugin)
        response = {plugin: {}}
        multigraph = plugin

        for current_line in self._iterline():
        
#            print "Line: %s\n" % current_line
#            print "Response start: %r" %response
        
            if current_line.startswith("multigraph "):
                multigraph = current_line[11:]
                response[multigraph] = {}
                continue

            try:
                key_name, key_value = current_line.split(" ", 1)
            except ValueError:
                # ignore broken plugins that don't return a value at all
                continue

            if "." in key_name:
                # Some keys have periods in them.
                # If so, make their own nested dictionary.
                key_root, key_leaf = key_name.split(".", 1)
#                print "Response . in key_name: %r\n" %response
                if key_root not in response[plugin]:
                    response[multigraph][key_root] = {}
#                print "multigraph: %r\nkey_root: %r\nkey_leaf: %r\nkey_value: %r\n" % (multigraph, key_root, key_leaf, key_value)
                response[multigraph][key_root][key_leaf] = key_value
            else:
#                print "%r\n" % response
                response[multigraph][key_name] = key_value

#            print "Response final: %r\n" %response

        return response

    def process_host_stats(self):
        """Process Munin node data, potentially sending to Carbon."""
        start_timestamp = time.time()
        self.logger.info("Thread %s: Querying host %s", self.hostname, self.hostname)
        # to be more efficient, load list of plugins just in case we do not have any
        if self.reload_plugins:
            self.plugins_config = {}
            self.plugins = self.list_plugins()
            self.set_reload_plugins(False)
            self.logger.debug("Thread %s: Plugin List: %s", self.hostname, self.plugins)
        epoch_timestamp = int(start_timestamp)

        for current_plugin in self.plugins:
            self.logger.info("Thread %s: Fetching plugin: %s (Host: %s)",
                        self.hostname, current_plugin, self.hostname)

            # after (re)load of list of plugins we have to load their configurations too
            try:
                self.plugins_config[current_plugin]
            except KeyError:
                self.plugins_config[current_plugin] = self.get_config(current_plugin)
                self.logger.debug("Thread %s: Plugin Config: %s", self.hostname, self.plugins_config[current_plugin])

            plugin_data = self.fetch(current_plugin)
            self.logger.debug("Thread %s: Plugin Data: %s", self.hostname, plugin_data)
            if self.args.carbon:
                for multigraph in self.plugins_config[current_plugin]:
                    print "\n>>>>>>>>>>>>>>>>>> current plugin: %s" % current_plugin
                    print ">>>>>>>>>>>>>>>>>> multigraph: %s" % multigraph
                    print ">>>>>>>>>>>>>>>>>> plugin_data: %r" % plugin_data
                    
                    try:
                        self.send_to_carbon(epoch_timestamp,
                                            current_plugin,
                                            self.plugins_config[current_plugin][multigraph],
                                            plugin_data[multigraph])
                    except KeyError:
                        self.logger.info("Thread %s: Plugin returns invalid data:\n plugin_config: %r host %s.",
                                    self.hostname, self.plugins_config[current_plugin], self.hostname)
        end_timestamp = time.time() - start_timestamp
        self.close_connection()
        self.close_carbon_connection()
        self.logger.info("Thread %s: Finished querying host %s (Execution Time: %.2f sec).",
                    self.hostname, self.hostname, end_timestamp)
        return end_timestamp

    def send_to_carbon(self, timestamp, plugin_name, plugin_config, plugin_data):
        """Send plugin data to Carbon over Pickle format."""
        if self.args.noprefix:
            prefix = ''
        else:
            prefix = "%s." % self.args.prefix

        hostname = self.hostname
        if self.remotenode:
            hostname = self.remotenode

        data_list = []
        self.logger.info("Creating metric for plugin %s, timestamp: %d",
                    plugin_name, timestamp)

        for data_key in plugin_data:
            try:
                plugin_category = plugin_config["graph_category"]
                metric = "%s%s.%s.%s.%s" % (prefix, self.displayname, plugin_category, plugin_name, data_key)
                value = plugin_data[data_key]
                self.logger.debug("Creating metric %s, value: %s", metric, value)
                data_list.append((metric, (timestamp, value)))
            except KeyError:
                self.logger.info("plugin returns invalid data:\n plugin_config: %r host %s.", plugin_config, self.hostname)

        if self.args.noop:
            self.logger.info("NOOP: Not sending data to Carbon")
            return

        self.logger.info("Sending plugin %s data to Carbon for host %s.", plugin_name, hostname)
        payload = pickle.dumps(data_list)
        header = struct.pack("!L", len(payload))
        message = header + payload
        try:
            self._carbon_sock.sendall(message)
            self.logger.info("Finished sending plugin %s data to Carbon for host %s.", plugin_name, self.hostname)
        except socket.error:
            self.logger.exception("Unable to send data to Carbon")


###
# Custom Threading class, one thread for each host in configuration
###
class MuninThread(threading.Thread):
    def __init__(self, params, cmdlineargs, logger=None):
        threading.Thread.__init__(self)
        self.name = params['host']

        # construct new namespace to pass it to the new Munin class instance
        # for better manipulation, just prepare writable dcfg "link" to new namespace
        cfg = argparse.Namespace()
        dcfg = vars(cfg)

        #construct final arguments Namespace
        for v in vars(cmdlineargs):
            try:
                dcfg[v] = params[v]
            except KeyError:
                dcfg[v] = getattr(cmdlineargs, v, None)

        if logger:
            self.logger = logger
        else:
            # if we have not provided a logger, let's create a very basic one
            self.logger = logging.getLogger()

        self.munin = Munin(hostname=self.name, args=cfg, logger=self.logger)

    def run(self):
        self.logger.info("Starting thread for %s." % self.name)
        self.munin.go()
        self.logger.info("Finishing thread for %s." % self.name)

    def dostop(self):
        self.logger.info("Thread %s: Got signal to stop." % self.name)
        self.munin.set_shutdown(True)

    def reload(self):
        self.logger.info("Thread %s: Got signal to reload." % self.name)
        self.munin.set_reload_plugins(True)

