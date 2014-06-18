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
config.prefix = 'munin.';


function searchESForNodes(config, searchTerm) {

    // Form up any query here
    // '{ "fields": [ "host", "prefix" ], "query": { "regexp": { "host": ".*" }}, "sort": { "host" : "asc" }}}'
    var esquery = '{"from" : 0, "size" : 1024, "fields": [ "host", "prefix", "displayname" ], "query": { "regexp": { "host": "' + searchTerm + '", "prefix": "'+config.prefix+'"}}}';

    // POST the query to ES
    var json = jQuery.ajax({
            url: config.es+config.muninnode_index+'/_search/',
            type: 'POST',
            crossDomain: true,
            dataType: json,
            data: esquery,
            async: false
        });

    // You can then do anything you like with this jsonData
    return jQuery.parseJSON(json.responseText);
}

function searchESForNodePlugins(config, searchTerm) {

    // Form up any query here
    var esquery = '{"query": { "match": { "host": "' + searchTerm + '"}}}';

    // POST the query to ES
    var json = jQuery.ajax({
            url: config.es+config.muninnode_index+'/_search/',
            type: 'POST',
            crossDomain: true,
            dataType: json,
            data: esquery,
            async: false
        });

    // You can then do anything you like with this jsonData
    return jQuery.parseJSON(json.responseText);
}

// function used by sort of plugins
function comparePluginsCategory(a, b) {
    var plugin_name_a = a['plugin_name']
    var plugin_name_b = b['plugin_name']
    var plugin_a_category = a['plugin'][plugin_name_a]['graph_category']+plugin_name_a;
    var plugin_b_category = b['plugin'][plugin_name_b]['graph_category']+plugin_name_b;
    var result = 0;

    plugin_a_category = plugin_a_category.toLowerCase();
    plugin_b_category = plugin_b_category.toLowerCase();
    if (plugin_a_category < plugin_b_category)
         result = -1;
    if (plugin_a_category > plugin_b_category)
        result = 1;

    return result;
}

// Setup variables
var node = '';
var node_key = '';
var def_linewidth = 1;
// Set a default timespan if one isn't specified
var timspan = '6h';
// Intialize a skeleton object of dashboard
var dashboard = {
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
    style: "light",
    nav: [{
        type: "timepicker",
        collapse: false,
        notice: false,
        enable: true,
        status: "Stable",
        time_options: [ "5m","15m","30m","1h","2h","3h","6h","12h","1d","2d","3d","4d","5d","7d","30d" ],
        refresh_intervals: [ "5s","10s","30s","1m","5m","15m","30m","1h","2h","1d" ],
        now: true
    }]
};

if(!_.isUndefined(ARGS.from)) {
    timspan = ARGS.from;
}
if(!_.isUndefined(ARGS.line)) {
    def_linewidth = parseInt(ARGS.line);
}

// fill in arguments provided from URL
if(!_.isUndefined(ARGS.node) && !_.isUndefined(ARGS.graphitekey) ) {
    node = ARGS.node;
    node_key = ARGS.graphitekey;

    // searchES() should return just 1 result with a node or empty set
    var data = searchESForNodePlugins(config, node);
    if (data.hits.total > 0) {
        // Set title of dashboard
        dashboard.title = 'Munin node dashboard - '+node;
        dashboard.services.filter = {
            time: {
                from: "now-" + timspan,
                to: "now"
            }
        };

        // here we've got plugins of matched node
        var plugins_temp = data.hits.hits[0]._source.plugins;
        var plugins = [];
        for (var pi in plugins_temp)
        {
            // we have got some (nested) multigraphs, lets put multigraph plugins directly to the plugins array
            if (plugins_temp[pi]['plugin']['ismultigraph'] == 1)
            {
                for (var mi in plugins_temp[pi]['plugin'])
                {
                    var multiplugin = plugins_temp[pi]['plugin'][mi];
                    if (multiplugin instanceof Object && "graph_title" in multiplugin)
                    {
                        // it is valid plugin not only a wrapper, so move on and copy it to plugins result array
                        var mgobj = {'plugin_name': mi, 'plugin': {'ismultigraph': 1}}
                        mgobj['plugin'][mi] = multiplugin;
                        mgobj['multigraphpath'] = plugins_temp[pi]['plugin_name']
                        plugins.push(mgobj);
                    }
                }
            }
            else
            {
                // simple graph, just copy it over to plugins result array
                plugins.push(plugins_temp[pi]);
            }
        }

        // we would like to have plugins sorted by graph category to be able to group them visually
        plugins = plugins.sort(comparePluginsCategory);

        var prefix = data.hits.hits[0]._source.prefix;
        var t, a, ds;
        var category = '';
        var cat_navigation = "";
        for (var i in plugins) {
            // get information about actual graph
            var plugin_name = plugins[i]['plugin_name']
            var plugin = plugins[i]['plugin'][plugin_name];

            var g_title = plugin['graph_title'] || 'Graph title not defined by plugin.';
            var g_infofound = false;
            var g_info = plugin['graph_info'] || '';
            var g_args = plugin['graph_args'] || '';
            var g_category = plugin['graph_category'] || 'misc';
            var g_period = plugin['graph_period'] || 'second';
            var g_order = plugin['graph_order'] || false;
            var g_vlabel = plugin['graph_vlabel'] || '';
            var g_linewidth = def_linewidth;
            var g_areafill = 2;
            var g_stacked = false;
            var g_left_y_format = "short"
            var g_upperlimit = null;
            var g_lowerlimit = null;
            var g_percentage = false;
            var g_aliascolors = {};

            // iterate through datasources and create targets as JSON struct
            ds = [];
            var tempds = {};
            var tempdslength = 0;

            if (g_info.localeCompare('') == 0) {
                g_info = 'Graph info not defined by plugin.';
            }
            else {
                g_infofound = true;
            }

            // browse through all datasources
            for (var d in plugin) {
                var ta = {};

                if (d.substr(0,6) != 'graph_') {
                    if ("ismultigraph" in plugins[i]['plugin'] && plugins[i]['plugin']['ismultigraph'] == 1)
                    {
                        t = prefix+'.'+node_key+'.'+g_category+'.'+plugins[i]['multigraphpath']+'.'+plugin_name+'.'+d;
                    }
                    else
                    {
                        t = prefix+'.'+node_key+'.'+g_category+'.'+plugin_name+'.'+d;
                    }
                    // how to interpret datapoints
                    //if ("type" in plugin[d] && plugin[d]["type"] == "DERIVE")
                    if (plugin[d].hasOwnProperty("type") && plugin[d]["type"] == "DERIVE") {
                        t = "derivative(" + t + ")";
                    }
                    if (plugin[d].hasOwnProperty("type") && plugin[d]["type"] == "COUNTER") {
                        t = "perSecond(" + t + ")";
                    }

                    // style of line/area
                    if (plugin[d].hasOwnProperty("draw") && plugin[d]["draw"].substr(0,9) == "AREASTACK")
                        g_stacked = true;
                    if (plugin[d].hasOwnProperty("draw") && plugin[d]["draw"].substr(0,5) == "STACK")
                        g_stacked = true;
                    if (plugin[d].hasOwnProperty("draw") && plugin[d]["draw"].substr(0,4) == "LINE")
                        g_linewidth = (parseInt(plugin[d]["draw"].substr(4)) || g_linewidth);
                    if (plugin[d].hasOwnProperty("draw") && plugin[d]["draw"].substr(0,4) == "AREA" && g_stacked == 'false')
                        g_areafill = (plugin[d]["draw"].substr(4) || 4);

                    // append information about datasource if any
                    if (plugin[d].hasOwnProperty("info")) {
                        if (g_infofound) {
                            g_info += "<br/><u>" + d + "</u> - " + plugin[d]["info"];
                        }
                        else {
                            g_info = "<br/><u>" + d + "</u> - " + plugin[d]["info"];
                            g_infofound = true;
                        }
                    }

                    a = plugin[d]["label"] || d;
                    if(plugin[d].hasOwnProperty("colour")) {
                        g_aliascolors[a] = "#"+ plugin[d]["colour"];
                    }
                    ta.target = "alias("+t+", '"+a+"')";
                    tempds[d]=JSON.parse(JSON.stringify(ta));
                    tempdslength++;
                }
            }

            // if there is defined specific order of metrics in graph, prepare targets in that order
            if (g_order) {
                g_order = g_order.split(/[\s]+/);
                // the order should be set not for all metrics within graph
                // so first add those ordered
                for (var oi=0; oi<g_order.length; oi++) {
                    if (oi< tempdslength) {
                        var ordi = g_order[oi];
                        ds.push(tempds[ordi]);
                    }
                }
                // and then add the rest of metrics not mentioned in graph_order
                // browse through all datasources again and add those not already in
                for (var tds in tempds) {
                    if (g_order && g_order.indexOf(tds) == -1 ) {
                        ds.push(tempds[tds]);
                    }
                }
            }
            else
            {
                // there is no explicit order of datasources, just copy it over
                ds = JSON.parse(JSON.stringify(tempds));
                g_order = "Not specified";
            }

            // modify units of y-axis in case there is any sign it could be of bytes or bits
            if (/bytes/i.test(g_vlabel) || /bytes/i.test(g_info))
                g_left_y_format = "bytes";
            if (/bits/i.test(g_vlabel) || /bits/i.test(g_info))
                g_left_y_format = "bits";

            // in case there is graph_period variable in description, do a replacement
            g_vlabel = g_vlabel.replace("\${graph_period}", g_period);

            // set correct options if defined in graph_args
            // upper limit
            var foo = g_args.match("(--upper-limit|-u) ([0123456789]+)");
            if( foo instanceof Array ) {
                g_upperlimit = foo[2];
                if (parseInt(foo[2]) == 100 && g_stacked) {
                    g_percentage = true;
                }
            }
            // lower limit
            foo = g_args.match("(--lower-limit|-l) ([0123456789]+)");
            if( foo instanceof Array ) {
                g_lowerlimit = foo[2];
            }

            // new category, let's create a visual panel for it
            if ( category != g_category ) {
                category = g_category;

                //cat_navigation = cat_navigation + "<a href='#"+category+"'>"+category+"</a> ";

                dashboard.rows.push({
                  title: "Category "+category+" row",
                  height: "50px",
                  editable: false,
                  collapse: false,
                  collapsable: false,
                  panels: [
                    {
                      error: false,
                      span: 12,
                      editable: true,
                      type: "text",
                      loadingEditor: false,
                      mode: "html",
                      content: "<a style='text-decoration: none' name='"+category+"' class='category'></a>" +
                          "<div style='background-color: white; " +
                          "color:cornflowerblue; text-align: center; font-size: 14px; " +
                          "border: 2px; text-transform: uppercase;' >"+category+"</div>",
                      style: {},
                      title: " "
                    }
                  ],
                  notice: false
                });
            }

            // prepare HTML snippet with plugin's information
            var plugin_information;
            plugin_information = '<div><ul style="list-style:none; padding-left: 0px; padding-bottom: 2px;">';
            plugin_information += '<li><strong>Name</strong>: ' + plugin_name + '</li>';
            plugin_information += '<li><strong>Info</strong>: ' + g_info + '</li>';
            plugin_information += '<li><strong>Datasources</strong>: '+ tempdslength +'</li>';
            plugin_information += '</ul></div>';

            // create rows with targets and appropriate configuration
            dashboard.rows.push({
                title: 'Chart for '+ plugin_name,
                height: '250px',
                panels: [{
                        title: 'Plugin information',
                        type: 'text',
                        span: 4,
                        fill: 1,
                        mode: "html",
                        content: plugin_information
                    },
                    {
                        title: g_title,
                        leftYAxisLabel: g_vlabel,
                        y_formats: [
                            g_left_y_format,
                            "short"
                        ],
                        type: 'graphite',
                        span: 8,
                        lines: true,
                        fill: g_areafill,
                        linewidth: g_linewidth,
                        points: false,
                        pointradius: 5,
                        bars: false,
                        stack: g_stacked,
                        tooltip: {
                            value_type: "individual",
                            query_as_alias: true
                          },
                        legend: {
                            show: true,
                            values: false,
                            min: false,
                            max: false,
                            current: false,
                            total: false,
                            avg: false
                        },
                        grid: {
                            max: g_upperlimit,
                            min: g_lowerlimit,
                            threshold1: null,
                            threshold2: null,
                            threshold1Color: "rgba(216, 200, 27, 0.27)",
                            threshold2Color: "rgba(234, 112, 112, 0.22)"
                        },
                        percentage: g_percentage,
                        aliasColors: g_aliascolors,
                        targets: ds
                    }]
                });
        }
    }
    else {
        dashboard.title = 'Munin node dashboard - '+node;
        dashboard.rows.push({
            title: 'Node '+node+' not found.',
            height: '300px',
            panels: [{
                title: 'Dashboard for '+node+'\'s munin plugins',
                type: 'text',
                span: 12,
                fill: 1,
                content: 'Node '+node+' not found.'
            }]
        });
  }
}
else {
    // search for all nodes stored in index, prepare filtering template
    var hosts = searchESForNodes(config, ".*");

    // populate nodes into list
    var nodes_list = "<ul>";
    for (var fnode in hosts.hits.hits) {
        var node_host;
        var node_key;

        if (hosts.hits.hits[fnode].fields.hasOwnProperty('host')) {
            node_host = hosts.hits.hits[fnode].fields.host[0];
        }
        if (hosts.hits.hits[fnode].fields.hasOwnProperty('displayname')) {
            node_key = hosts.hits.hits[fnode].fields.displayname[0];
        }
        nodes_list += "<li><a href='"+window.location+"?node="+node_host+"&graphitekey="+node_key+"'>"+node_host+"</a></li>";
    }
    nodes_list += "</ul>";

    dashboard.title = 'Munin nodes list';
    dashboard.rows.push({
        title: 'List of configured nodes',
        height: '300px',
        panels: [{
            title: 'List of configured nodes',
            span: 12,
            fill: 1,
            type: 'text',
            mode: 'html',
            content: nodes_list
        }]
    });
}

return dashboard;
