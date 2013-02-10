# munin-graphite

Collect Munin statistics, and convert their naming structure to submit to Graphite for visualization.

## Requirements

* Munin
* Python
* Graphite (with a Carbon cache or relay)

## Installation

Clone the Git repository from [https://github.com/jforman/munin-graphite](https://github.com/jforman/munin-graphite)

## Example

As of 20130209, the poller is best configured via a Cronjob that runs once a minute. 

    ./m2g-poller.py --muninhost localhost --carbon carbonhost:2004
    
Metrics paths are created using the hostname and various plugin data. The processes count plugin for Munin would produce metrics and values like the following:

    servers.localhost.processes.processes.uninterruptible, value: 0
    servers.localhost.processes.processes.processes, value: 224
    servers.localhost.processes.processes.runnable, value: 3
    servers.localhost.processes.processes.dead, value: 0
    servers.localhost.processes.processes.sleeping, value: 221
    servers.localhost.processes.processes.zombie, value: 0
    servers.localhost.processes.processes.paging, value: 0
    servers.localhost.processes.processes.stopped, value: 0

These paths of data are then sent to Carbon via the pickle port. 

## TODO

Logic will eventually be added to allow the m2g-poller to be run in the background with a list of hosts to query and not require a cronjob.
