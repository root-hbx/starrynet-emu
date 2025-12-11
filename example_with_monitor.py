#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
StarryNet: empowering researchers to evaluate futuristic integrated space and terrestrial networks.
Example with real-time monitoring enabled.
"""

from starrynet.sn_observer import *
from starrynet.sn_orchestrater import *
from starrynet.sn_synchronizer import *
from d2c_extension import RTMonitor

if __name__ == "__main__":
    # Starlink 10*10: 100 satellite nodes, 10 ground stations.
    # The node index sequence is: 1-100 sattelites, 101-110 ground stations.
    # In this example, 100 satellites and 10 ground stations are one AS.

    # Node #1 to Node #110 are within the same AS.
    # 1-100: satellites, 101-110: ground stations
    AS = [[1, 110]]
    # latitude and longitude of frankfurt, Austria, Paris, London, New York, Beijing, Los Angeles, Tokyo, Moscow, Rome
    GS_lat_long = [
        [50.110924, 8.682127],
        [46.635700, 14.311817],
        [48.856613, 2.352222],
        [51.507351, -0.127758],
        [40.712776, -74.005974],
        [39.931910, 116.403112],
        [34.052235, -118.243683],
        [35.689487, 139.691711],
        [55.755825, 37.617298],
        [41.902782, 12.496366]
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
    dst_gs_1 = 106
    src_gs_2 = 102
    dst_gs_2 = 107
    src_gs_3 = 103
    dst_gs_3 = 108
    src_gs_4 = 104
    dst_gs_4 = 109
    src_gs_5 = 105
    dst_gs_5 = 110

    monitoring_pairs = [
        (src_gs_1, dst_gs_1, "gs", "gs"),
        (src_gs_2, dst_gs_2, "gs", "gs"),
        (src_gs_3, dst_gs_3, "gs", "gs"),
        (src_gs_4, dst_gs_4, "gs", "gs"),
        (src_gs_5, dst_gs_5, "gs", "gs")
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
