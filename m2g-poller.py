#!/usr/bin/python

## TODO: Plugin output seems intermingled
## with the wrong plugin name

#from multiprocessing import Pool
#from datetime import datetime
import time
import socket


hostlist = ["localhost"]

class Munin():
    def __init__(self, hostname="localhost", port=4949):
        self.hostname = hostname
        self.port = port

    def connect(self):
        # Use getdefaulttimeout() to figure out what the default timeout is.
        self._sock = socket.create_connection((self.hostname, self.port), 10)
        self._conn = self._sock.makefile()
        self.hello_string = self._readline()

    def _readline(self):
        return self._conn.readline().strip()

    def _iterline(self):
        while True:
            current_line = self._readline()
            if not current_line:
                break
            if current_line.startswith("#"):
                continue
            if current_line == ".":
                break
            yield current_line

    def fetch(self, plugin):
        self._sock.sendall("fetch %s\n" % plugin)
        plugin_data = {}
        while True:
            data = self._sock.recv(1024)
            if not data:
                break
            response += data

        return response

    def close_connection(self):
        self._sock.close()

    def list_plugins(self):
        """Return a list of munin plugins configured on a node. """
        self._sock.sendall("list\n")
        return self._readline().split(" ")

    def get_config(self, plugin):
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

    def get_fetch(self, plugin):
        self._sock.sendall("fetch %s\n" % plugin)
        response = {}
        for current_line in self._iterline():
            full_key_name, key_value = current_line.split(" ")
            key_name = full_key_name.split(".")[0]
            response[key_name] = key_value

        return response
            

    def process_host_stats(self):
        """Given a Munin object, process its host data."""
        plugins = self.list_plugins()
        #print "Plugin List: %s" % plugins
        for current_plugin in plugins:
            #print "---------------"
            #print "Fetching plugin: %s" % current_plugin
            config = self.get_config(current_plugin)
            #print "Plugin config: %s" % config
            plugin_data = self.get_fetch(current_plugin)
            #print "Plugin data: %s" % plugin_data
            time.sleep(0.5)


if __name__ == '__main__':
    for current_host in hostlist:
        print "querying host: %s" % current_host
        munin_host = Munin(hostname=current_host)
        munin_host.connect()
        munin_host.process_host_stats()
        munin_host.close_connection()
        print "done querying host %s" % current_host
