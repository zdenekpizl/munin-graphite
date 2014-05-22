# munin-graphite

Collect Munin statistics, and convert their naming structure to submit to Graphite for visualization.

## Requirements

* Munin
* Python
* Graphite (with a Carbon cache or relay)

## Installation

Clone the Git repository from [https://github.com/jforman/munin-graphite](https://github.com/jforman/munin-graphite)

## Program invocation

Optimal way is to run m2g-poller using **nohup** and define all hosts within an configuration file:

Example:
nohup ./m2g-poller.py --config /etc/munin-graphite/hosts.cfg &


## Configuration file looks like:
```
[node-001]
carbon=carbon01.company.com:2004
host=node-001.infra.company.com
interval=60
prefix=munin

[node-002]
carbon=carbon99.company.com:2004
host=node-002.infra.company.com
interval=120
prefix=munin
```
Runing with config above will start two threads, each thread for one node's section and these threads will in defined
intervals fetch data from munin-node on targets.

If you do not specify all parameters they will be set to default values as described in --help option.

You can run m2g-poller.py from commandline with parameters directly to override some or all of supported options,
in that case all specified option will be use instead of built-in defaults for nodes in configuration file.

Example:
./m2g-poller.py --host node-003.company.com --displayname node-003 --carbon carbon01.infra.company.com:2004 --interval 90 --prefix someprefix

## Signal handling

* you can send SIGTERM to m2g-poller.py program. This would terminate program's run after all threads will finish its
  current cycle.
* pressing CTRL+C when running from command line will terminate the program as well.
* you can send SIGHUP to m2g-poller.py program. This would signalize the program it should reload list of plugins of all
  nodes from target list.

## System log

Program logs information into syslog, using prefix MUNIN-GRAPHITE and identification of originating thread.

Example:
MUNIN-GRAPHITE: INFO Thread node-009.company.com: Finished querying host node-009.company.com (Execution Time: 5.12 sec).

## Metrics

Metrics paths are created using the hostname and various plugin data. The processes count plugin for Munin would produce
metrics and values like the following:

    servers.localhost.processes.processes.uninterruptible, value: 0
    servers.localhost.processes.processes.processes, value: 224
    servers.localhost.processes.processes.runnable, value: 3
    servers.localhost.processes.processes.dead, value: 0
    servers.localhost.processes.processes.sleeping, value: 221
    servers.localhost.processes.processes.zombie, value: 0
    servers.localhost.processes.processes.paging, value: 0
    servers.localhost.processes.processes.stopped, value: 0

These paths of data are then sent to Carbon via the pickle port. 

