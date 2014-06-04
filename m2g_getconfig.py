#!/usr/bin/python
"""Gather Munin statistics and deliver to Carbon for Graphite display."""

import argparse
import ConfigParser
import logging
import logging.handlers
import re
import sys
import m2g_munin_thread
import elasticsearch as ES

RE_LEFTRIGHT = re.compile(r"^(?P<left>\S+)\s+(?P<right>\S+)$")
RE_MUNIN_NODE_NAME = re.compile(r"^# munin node at\s+(?P<nodename>\S+)$")


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
    parser.add_argument("--es",
                        action="store",
                        help="ElasticSearchServer:Port port (ex: localhost:9200).")
    parser.add_argument("--esindex",
                        action="store",
                        default="gd-munin-node",
                        help="ElasticSearch document index. Default: %(default)s.")
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


def main():
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

    hosts = list()
    if args.config:
        hosts = read_configuration(args.config)
    if not hosts:
        # no file configuration, trying to use commandline arguments only and construct one-item dictionary
        hosts.append({'host': args.host})
        # we have got some items in hosts's list

    for host in hosts:
        cfg = argparse.Namespace()
        dcfg = vars(cfg)

        #construct final arguments Namespace
        for v in vars(args):
            try:
                dcfg[v] = host[v]
            except KeyError:
                dcfg[v] = getattr(args, v, None)

        plugins_config = {}
        hostplugins = []
        munin = m2g_munin_thread.Munin(hostname=host['host'], args=cfg, logger=logger)
        munin.connect()
        munin.update_hostname()
        plugins = munin.list_plugins()
        for current_plugin in plugins:
            try:
                plugins_config[current_plugin]
            except KeyError:
                plugins_config["plugin"] = munin.get_config(current_plugin)
                plugins_config["plugin_name"]=current_plugin
                hostplugins.append(plugins_config.copy())
                print "  Config %s: %s" % (current_plugin,plugins_config)
                logger.debug("Thread %s: Plugin Config: %s", munin.hostname, plugins_config)

        host['prefix'] = cfg.prefix
        host['plugins'] = hostplugins
        if cfg.displayname:
            host['host'] = cfg.displayname

    try:
        es = ES.Elasticsearch(args.es, sniff_on_start=False)
        for host in hosts:
            nodeid = host['prefix']+"."+host['host']
            res = es.index(index=args.esindex, id=nodeid, doc_type='node', body=host)
            print res
    except Exception as e:
            print "Error: %r" % e
            logger.debug("Thread %s: Cannot connect to ElasticSearch server: %s", args.es)


if __name__ == '__main__':
    main()
