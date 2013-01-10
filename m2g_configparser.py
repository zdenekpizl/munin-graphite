#!/usr/bin/env python

import ConfigParser
import sys

class M2GConfigParser():
    def __init__(self, config_path):
        self._config_path = config_path
        self._config_dict = {} # The entire file parsed into a dictionary.
        self._graphite_config = {} # The data we'll use for Munin queries.
        self._parsed_config = ConfigParser.SafeConfigParser()
        self._parsed_config.read(self._config_path)

    def parse_config(self):
        """Parse out all the config's data."""
        self.set_config_dict()
        self.set_host_list()

    def set_config_dict(self):
        """Populate the object's dictionary from the config file."""
        sections = self._parsed_config.sections()
        for current_section in sections:
            options = self._parsed_config.options(current_section)
            self._config_dict[current_section] = {}
            for current_option in options:
                self._config_dict[current_section][current_option] = self._parsed_config.get(current_section, current_option)

    def get_config_dict(self):
        return self._config_dict

    def set_host_list(self):
        """From a parsed config, list the computed Graphite host list."""
        for section in self._config_dict:
            self._graphite_config[section] = {}
            # Set Hostname to query first
            if "address" in self._config_dict[section]:
                self._graphite_config[section]["address"] = self._config_dict[section]["address"]
            else:
                self._graphite_config[section]["address"] = section

            # Set graphitename to display in Graphite
            if "graphitename" in self._config_dict[section]:
                self._graphite_config[section]["graphitename"] = self._config_dict[section]["graphitename"]
            else:
                self._graphite_config[section]["graphitename"] = section.split(".")[0]

    def get_graphite_config(self):
        return self._graphite_config
    
if __name__ == "__main__":
    myconfig = M2GConfigParser(sys.argv[1])
    myconfig.parse_config()
    print "Graphite Config: %r" % myconfig.get_graphite_config()
