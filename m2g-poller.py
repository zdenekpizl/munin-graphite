#!/usr/bin/python
"""Gather Munin statistics and deliver to Carbon for Graphite display."""

import argparse
import ConfigParser
import logging
import logging.handlers
import re
import sys
import time
import signal
import m2g_munin_thread

RE_LEFTRIGHT = re.compile(r"^(?P<left>\S+)\s+(?P<right>\S+)$")
RE_MUNIN_NODE_NAME = re.compile(r"^# munin node at\s+(?P<nodename>\S+)$")

threads = []

###
# bellow are common function
###
def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Send Munin statistics to Graphite.")
    parser.add_argument("--config", "-c",
                        action="store",
                        default=False,
                        help="Configuration file with list of hosts and their plugins to fetch.")
    parser.add_argument("--host",
                        action="store",
                        default="localhost",
                        help="Munin host to query for stats. You can specify indirect node after ':', "
                             "i.e. --host localhost:remotenode. Default: %(default)s")
    parser.add_argument("--displayname",
                        default=False,
                        help="If defined, use this as the name to store metrics in Graphite instead of the Munin"
                             " hostname.")
    parser.add_argument("--carbon",
                        action="store",
                        help="Carbon host and Pickle port (ex: localhost:2004).")
    parser.add_argument("--filter",
                        action="store",
                        default='.*',
                        help="Regular expression for selecting only defined subset of received plugins.")
    parser.add_argument("--interval",
                        type=int,
                        default=60,
                        help="Interval (seconds) between polling Munin host for statistics. If set to 0, exit after "
                             "polling once. Default: %(default)s")
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
    parser.add_argument("--logtosyslog",
                        action="store_true",
                        help="Log to syslog. No output on the command line.")
    parser.add_argument("--verbose", "-v",
                        choices=[1, 2, 3],
                        default=2,
                        type=int,
                        help="Verbosity level. 1:ERROR, 2:INFO, 3:DEBUG. Default: %(default)d")

    args = parser.parse_args()
    return args


###
# stop all threads and exit
###
def handler_term(signum=signal.SIGTERM, frame=None):
    global threads

    for t in threads:
        t.dostop()


###
# set all threads to reload information about all munin-node's plugins
###
def handler_hup(signum, frame=None):
    global threads

    for t in threads:
        t.reload()


def read_configuration(configfile):
    """
    Returns False if configuration file is not readable, list of dictionaries otherwise

    Configuration options follow parameters described as command line options. All parameters are optional except host,
    displayname parameter is built from section name, so it is always presented too.

    Non-existent options are superseded by defaults

    Example:
    [servername]
    host=fqdn[:remotenode]
    port=4949
    carbon=carbonhostfqdn:port
    interval=60
    prefix=prefix for Graphite's target
    noprefix=True|False
    filter=^cpu.*

    @param configfile: full filepath to configuration file
    @rtype : object
    """

    cf = ConfigParser.ConfigParser()
    hostscfg = []
    try:
        cf.read(configfile)
        for section in cf.sections():
            di = {}
            for ki, vi in cf.items(section):
                # construct dictionary item
                di[ki] = vi
            if "host" in di.keys():
                di["displayname"] = section
                hostscfg.append(di)
    except ConfigParser.Error as e:
        logger.critical("Failed to parse configuration or command line options. Exception was %s. Giving up." % e)

    return hostscfg

def list_plugins(self):
    """Return a list of Munin plugins configured on a node. """
    self._sock.sendall("cap multigraph\n")
    self._readline()  # ignore response

    if self.remotenode:
        self.thread.logger.info("Thread %s: Asking for plugin list for remote node %s", self.thread.name, self.remotenode)
        self._sock.sendall("list %s\n" % self.remotenode)
    else:
        self.thread.logger.info("Thread %s: Asking for plugin list for local node %s", self.thread.name, self.hostname)
        self._sock.sendall("list\n")

    plugin_list = self._readline().split(" ")
    if self.args.filter:
        try:
            filteredlist = [plugin for plugin in plugin_list if re.search(self.args.filter, plugin, re.IGNORECASE)]
            plugin_list = filteredlist
        except re.error:
            self.thread.logger.info("Thread %s: Filter regexp for plugin list is not valid: %s" % self.args.filter)
        # if there is no filter or we have got an re.error, simply return full list
    result_list = []
    for plugin in plugin_list:
        if len(plugin.strip()) > 0:
            result_list.append(plugin)
    return result_list

def get_config(self, plugin):
    """Get config values for Munin plugin."""
    self._sock.sendall("config %s\n" % plugin)
    response = {None: {}}
    multigraph = None

    for current_line in self._iterline():
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
            if key_root not in response:
                response[multigraph][key_root] = {}
            response[multigraph][key_root][key_leaf] = key_value
        else:
            response[multigraph][key_name] = key_value

    return response



def main():
    global threads
    global logger

    args = parse_args()
    if args.verbose == 1:
        logging_level = logging.ERROR
    elif args.verbose == 3:
        logging_level = logging.DEBUG
    else:
        logging_level = logging.INFO

    #logging.basicConfig(format=LOGGING_FORMAT, level=logging_level)
    logger = logging.getLogger()
    logger.setLevel(logging_level)
    syslog = logging.handlers.SysLogHandler(address='/dev/log')
    stdout = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('MUNIN-GRAPHITE: %(levelname)s %(message)s')
    syslog.setFormatter(formatter)
    if args.logtosyslog:
        logger.addHandler(syslog)
    else:
        logger.addHandler(stdout)

    # block for setting handling of signals
    signal.signal(signal.SIGHUP, handler_hup)
    signal.signal(signal.SIGTERM, handler_term)
    signal.signal(signal.SIGINT, handler_term)

    hosts = list()
    if args.config:
        hosts = read_configuration(args.config)
    if not hosts:
        # no file configuration, trying to use commandline arguments only and construct one-item dictionary
        hosts.append({'host': args.host})
        # we have got some items in hosts's list
    for host in hosts:
        logging.info("Going to thread with config %s" % host)
        threads.append(m2g_munin_thread.MuninThread(host, args, logger))

    for t in threads:
        t.start()

    while True:
        try:
            if not any([t.isAlive() for t in threads]):
                logging.info("All threads finished, exiting.")
                break
            else:
                time.sleep(1)
        except KeyboardInterrupt:
            handler_term()


if __name__ == '__main__':
    main()
