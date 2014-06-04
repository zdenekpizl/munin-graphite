/* global _ */

/*
 * Complex scripted dashboard
 * This script generates a dashboard object that Grafana can load. It also takes a number of user
 * supplied URL parameters (int ARGS variable)
 *
 * Global accessable variables
 * window, document, $, jQuery, ARGS, moment
 *
 * Return a dashboard object, or a function
 *
 * For async scripts, return a function, this function must take a single callback function,
 * call this function with the dasboard object
 */

'use strict';

// accessable variables in this scope
var window, document, ARGS, $, jQuery, moment, kbn;

var config = [];
config.muninnode_index = 'gd-munin-node';
config.es = 'http://poc-render01.na.getgooddata.com:9200/';


function searchES(config, searchTerm) {
  // Form up any query here
  var esquery;
  
  esquery = '{"query": { "match": { "host": "' + searchTerm + '"}}}';
  
  // POST the query to ES
  var json = jQuery.ajax({
    url: config.es+config.muninnode_index+'/_search/',
    type: 'POST',
    crossDomain: true,
    dataType: json,
    data: esquery,
    async: false
  });
  
  var jsonData = jQuery.parseJSON(json.responseText);
  // You can then do anything you like with this jsonData
  return jsonData;
}


return function(callback) {

  // Setup some variables
  var dashboard, timspan;

  // Set a default timespan if one isn't specified
  timspan = '1d';

  // Intialize a skeleton with nothing but a rows array and service object
  dashboard = {
    rows : [],
    services : {},
    loader: {
      save_gist: false,
      save_elasticsearch: true,
      save_local: true,
      save_default: true,
      save_temp: true,
      save_temp_ttl_enable: true,
      save_temp_ttl: "30d",
      load_gist: false,
      load_elasticsearch: true,
      load_elasticsearch_size: 20,
      load_local: false,
      hide: false
    },
    refresh: "5m",
    tags: [ "munin-auto-generated" ],
    timezone: "browser",
    hideControls: false,
    editable: true,
    failover: false,
    panel_hints: true,
    style: "dark",
    nav: [ 
    {
      type: "timepicker",
      collapse: false,
      notice: false,
      enable: true,
      status: "Stable",
      time_options: [ "5m","15m","30m","1h","2h","3h","6h","12h","1d","2d","3d","4d","5d","7d","30d" ],
      refresh_intervals: [ "5s","10s","30s","1m","5m","15m","30m","1h","2h","1d" ],
      now: true
     },
   ]
            
  };


  var node = "not defined";
  var seriesName = 'argName';

  if(!_.isUndefined(ARGS.node)) {
    node = ARGS.node;
  }

  var data = searchES(config, node);
  if (data.hits.total > 0) 
  {
   // Set a title
   dashboard.title = 'Munin node dashboard - all plugins - '+node;
   dashboard.services.filter = {
    time: {
      from: "now-" + (ARGS.from || timspan),
      to: "now"
    }
   };

   // here we've got plugins
   var plugins = data.hits.hits[0]._source.plugins;
   var prefix = data.hits.hits[0]._source.prefix;
   var ds;
   for (var plugin in plugins) {
     var panels = [];
    
     // get some information about actual graph
     var p = plugins[plugin];
     var g_title = p[plugin]['graph_title'];
     var g_category = p[plugin]['graph_category'];
     
     // iterate through datasources and create targets as JSON struct
     var t;
     var a;
     ds = [];
     for (var d in p[plugin]) {
       var ta = {};
       if (d.substr(0,6) != 'graph_') {
         t = prefix+'.'+node+'.'+g_category+'.'+plugin+'.'+d;
         if ("type" in p[plugin][d] && p[plugin][d]["type"] == "DERIVE")
           t = "derivative(" + t + ")"; 
         a = p[plugin][d]["label"];
         ta.target = "alias("+t+", '"+a+"')";
         ds.push(JSON.parse(JSON.stringify(ta)));
       }
     }
      
    // create rows with targets and appropriate configuration
    dashboard.rows.push({
      title: 'Chart for '+ plugin,
      height: '250px',
      panels: [
        {
          title: 'Plugin information',
          type: 'text',
          span: 3,
          fill: 1,
          content: 'Plugin name: '+ plugin + '\n' + 'Plugin category: '+g_category,
        },
        {
          title: g_title,
          type: 'graphite',
          span: 9,
          fill: 1,
          linewidth: 2,
          targets: ds,
        }
      ]
    });
    
    }

   callback(dashboard);
  }
  else
  {
    dashboard.title = 'Munin node dashboard - '+node;

    dashboard.rows.push({
      title: 'Node '+node+' not found.',
      height: '300px',
      panels: [
        {
          title: 'Dashboard for '+node+'\'s munin plugins',
          type: 'text',
          span: 12,
          fill: 1,
          content: 'Node '+node+' not found.'
        }
      ]
    });

   callback(dashboard);

  } 


  callback(dashboard);

}
