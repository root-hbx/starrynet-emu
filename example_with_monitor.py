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
    # Starlink 5*5: 25 satellite nodes, 2 ground stations.
    # The node index sequence is: 25 sattelites, 2 ground stations.
    # In this example, 25 satellites and 2 ground stations are one AS.

    AS = [[1, 27]]  # Node #1 to Node #27 are within the same AS.
    GS_lat_long = [
        [50.110924, 8.682127], [46.635700, 14.311817]
    ]  # latitude and longitude of frankfurt and  Austria
    configuration_file_path = "./config.json"
    hello_interval = 1  # hello_interval(s) in OSPF. 1-200 are supported.

    print('Start StarryNet.')
    sn = StarryNet(configuration_file_path, GS_lat_long, hello_interval, AS)
    sn.create_nodes()
    sn.create_links()
    sn.run_routing_deamon()

    # Start real-time monitoring after routing daemon is running
    # Demo: gs -> constellation -> gs
    src_gs = 26
    dst_gs = 27
    monitoring_pairs = [
        (src_gs, dst_gs, "gs", "gs"),
    ]

    # NOTE: Start monitoring with 1-second interval
    # S: 2Ghz | Ka: 30Ghz | Ku: 14Ghz
    monitor = RTMonitor(sn, carrier_frequency_hz=30e9) # Ka
    monitor.start(
        interval=1,
        node_pairs=monitoring_pairs
    )

    sn.start_emulation()

    # NOTE: Stop monitor
    monitor.stop()

    sn.stop_emulation()
