#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
StarryNet: empowering researchers to evaluate futuristic integrated space and terrestrial networks.
Example with real-time monitoring enabled.
"""

from starrynet.sn_observer import *
from starrynet.sn_orchestrater import *
from starrynet.sn_synchronizer import *
from rt_monitor import RTMonitor

if __name__ == "__main__":
    # Starlink 10*10: 100 satellite nodes, 6 ground stations.
    # The node index sequence is: 100 sattelites, 6 ground stations.
    # In this example, 100 satellites and 6 ground stations are one AS.

    # Node #1 to Node #106 are within the same AS.
    # 1-100: satellites, 101-106: ground stations
    AS = [[1, 106]]
    # latitude and longitude of frankfurt, Austria, Paris, London, New York, Beijing
    GS_lat_long = [
        [50.110924, 8.682127],
        [46.635700, 14.311817],
        [48.856613, 2.352222],
        [51.507351, -0.127758],
        [40.712776, -74.005974],
        [39.931910, 116.403112]
    ]
    configuration_file_path = "./config.json"
    hello_interval = 1  # hello_interval(s) in OSPF. 1-200 are supported.

    print('Start StarryNet.')
    sn = StarryNet(configuration_file_path, GS_lat_long, hello_interval, AS)
    sn.create_nodes()
    sn.create_links()
    sn.run_routing_deamon()

    # Start real-time monitoring after routing daemon is running
    # Demo: Multiple gs-gs pairs monitoring
    src_gs_1 = 101
    dst_gs_1 = 104
    src_gs_2 = 102
    dst_gs_2 = 105
    src_gs_3 = 103
    dst_gs_3 = 106

    monitoring_pairs = [
        (src_gs_1, dst_gs_1, "gs", "gs"),
        (src_gs_2, dst_gs_2, "gs", "gs"),
        (src_gs_3, dst_gs_3, "gs", "gs")
    ]

    # NOTE: Start monitoring with 1-second interval
    # S: 2Ghz | Ka: 30Ghz | Ku: 14Ghz
    # Each pair will have its own log file: rt_log_..._{src_gs}-{dst_gs}.txt
    monitor = RTMonitor(sn, log_dir=".", carrier_frequency_hz=30e9)  # Ka
    monitor.start(
        interval=1,
        node_pairs=monitoring_pairs
    )

    sn.start_emulation()

    # NOTE: Stop monitor
    monitor.stop()

    sn.stop_emulation()
