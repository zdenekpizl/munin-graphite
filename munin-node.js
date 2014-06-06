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

    // TODO sort plugings by category and plugin's name
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

var func = function(callback) {

    // Setup variables
    var node = '';
    var def_linewidth = 2;
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

    // fill in arguments provided from URL
    if(!_.isUndefined(ARGS.node)) {
        node = ARGS.node;
    }
    if(!_.isUndefined(ARGS.from)) {
        timspan = ARGS.from;
    }
    if(!_.isUndefined(ARGS.line)) {
        def_linewidth = parseInt(ARGS.line);
    }

    // searchES() should return just 1 result with a node or empty set
    var data = searchES(config, node);
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
    var plugins = data.hits.hits[0]._source.plugins;
    var prefix = data.hits.hits[0]._source.prefix;
    var t, a, ds;
   for (var plugin in plugins) {
        // get information about actual graph
        var p = plugins[plugin];
        var g_title = p[plugin]['graph_title'];
        var g_info = p[plugin]['graph_info'] || '';
        var g_args = p[plugin]['graph_args'] || '';
        var g_category = p[plugin]['graph_category'] || 'misc';
        var g_period = p[plugin]['graph_period'] || 'second';
        var g_order = p[plugin]['graph_order'] || false;
        var g_linewidth = def_linewidth;
        var g_areafill = 1;
        var g_stacked = false;
        var g_left_y_format = "short"
        var g_vlabel = p[plugin]['graph_vlabel'] || '';
        var g_upperlimit = null;
        var g_lowerlimit = null;
        var g_percentage = false;
        var g_aliascolors = {};

        // iterate through datasources and create targets as JSON struct
        ds = [];
        var tempds = {};
        tempds.length = 0;

        for (var d in p[plugin]) {
            var ta = {};

            if (d.substr(0,6) != 'graph_') {
                t = prefix+'.'+node+'.'+g_category+'.'+plugin+'.'+d;
                // how to interpret datapoints
                // TODO templates/filters, cdef (optionaly)
                if ("type" in p[plugin][d] && p[plugin][d]["type"] == "DERIVE")
                    t = "derivative(" + t + ")";
                if ("type" in p[plugin][d] && p[plugin][d]["type"] == "COUNTER")
                    t = "perSecond(" + t + ")";

                // style of line/area
                if ("draw" in p[plugin][d] && p[plugin][d]["draw"].substr(0,9) == "AREASTACK")
                    g_stacked = true;
                if ("draw" in p[plugin][d] && p[plugin][d]["draw"].substr(0,5) == "STACK")
                    g_stacked = true;
                if ("draw" in p[plugin][d] && p[plugin][d]["draw"].substr(0,4) == "LINE")
                    g_linewidth = (parseInt(p[plugin][d]["draw"].substr(4)) || g_linewidth);
                if ("draw" in p[plugin][d] && p[plugin][d]["draw"].substr(0,4) == "AREA" && g_stacked == 'false')
                    g_areafill = (p[plugin][d]["draw"].substr(4) || 4);

                a = p[plugin][d]["label"] || d;
                if("colour" in p[plugin][d]) {
                    g_aliascolors[a] = "#"+ p[plugin][d]["colour"];
                }
                ta.target = "alias("+t+", '"+a+"')";
                //ds.push(JSON.parse(JSON.stringify(ta)));
                tempds[d]=JSON.parse(JSON.stringify(ta));
                tempds.length++;
            }
        }

        // there is
        // if there is defined specific order of metrics in graph, prepare targets in that order
        if (g_order) {
            g_order = g_order.split(/[\s]+/);
            // the order should be set not for all metrics within graph
            // so first add those ordered
            for (var i=0; i<g_order.length; i++) {
                if (i< tempds.length) {
                    var ordi = g_order[i];
                    ds.push(tempds[ordi]);
                }
            }
        }
        // and then add the rest of metrics not mentioned in graph_order
        for (var t in tempds) {
            if (g_order.indexOf(t) == -1 ) {
                var ordi = tempds[t];
                ds.push(tempds[ordi]);
            }
        }

}

        // modify units of y-axis in case there is any sign it could be of bytes or bits
        if (/bytes/i.test(g_vlabel) || /bytes/i.test(g_info))
            g_left_y_format = "bytes";
        if (/bits/i.test(g_vlabel) || /bits/i.test(g_info))
            g_left_y_format = "bytes";

        // in case there is graph_period variable in description, do a replacement
        g_vlabel = g_vlabel.replace("\${graph_period}", g_period);

        // set correct options if defined in graph_args
        // upper limit
        var foo = g_args.match("(--upper-limit|-u) ([0123456789]+)");
        if( foo instanceof Array ) {
            g_upperlimit = foo[2];
            if (parseInt(foo[2]) == 100) {
                g_percentage = true;
            }
        }
        foo = g_args.match("(--lower-limit|-l) ([0123456789]+)");
        if( foo instanceof Array ) {
            g_lowerlimit = foo[2];
        }

        // create rows with targets and appropriate configuration
        dashboard.rows.push({
            title: 'Chart for '+ plugin,
            height: '250px',
            panels: [{
                    title: 'Plugin information',
                    type: 'text',
                    span: 3,
                    fill: 1,
                    content: 'Plugin name: '+ plugin + '\n' + 'Plugin category: '+g_category
                },
                {
                    title: g_title,
                    leftYAxisLabel: g_vlabel,
                    y_formats: [
                        g_left_y_format,
                        "short"
                    ],
                    type: 'graphite',
                    span: 9,
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

       callback(dashboard);
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

        callback(dashboard);
  }

  callback(dashboard);
}

return func;
