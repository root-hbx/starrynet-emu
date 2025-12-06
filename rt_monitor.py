#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
Real-time monitoring module for StarryNet
Monitors RTT between nodes with both wall-clock time and emulation time
"""

import threading
import time
import re
from datetime import datetime


class RTMonitor:
    """Real-time monitor for StarryNet emulation"""

    def __init__(self, starrynet_instance, log_file=None):
        """
        Initialize the real-time monitor

        Args:
            starrynet_instance: StarryNet instance to monitor
            log_file: Path to log file (default: ./rt_log_<timestamp>.txt)
        """
        self.sn = starrynet_instance
        self.running = False
        self.monitor_thread = None
        self.emulation_time = 0  # Track emulation time in seconds
        self.start_wall_time = None  # Wall clock time when emulation starts

        # Generate log file name with timestamp if not provided
        if log_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file = f"./rt_log_{timestamp}.txt"
        else:
            self.log_file = log_file

        # Initialize log file
        with open(self.log_file, 'w') as f:
            f.write("StarryNet Real-time Monitor Log\n")
            f.write(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

    def measure_rtt(self, node1_index, node2_index):
        """
        Measure RTT between two nodes using ping

        Args:
            node1_index: Index of first node
            node2_index: Index of second node

        Returns:
            RTT in milliseconds, or None if ping failed
        """
        try:
            # Get IP address of node2
            ip_list = self.sn.get_IP(node2_index)
            if not ip_list or len(ip_list) == 0:
                return None

            target_ip = ip_list[0]

            # Ping: node1 to node2
            cmd = f"docker exec ovs_container_{node1_index} ping -c 1 -W 1 {target_ip}"
            result = self.sn.remote_ssh.exec_command(cmd, get_pty=True)
            stdin, stdout, stderr = result
            output = stdout.read().decode('utf-8')

            # Parse RTT from ping output
            # Looking for pattern like "time=XX.X ms"
            match = re.search(r'time=([\d.]+)\s*ms', output)
            if match:
                rtt = float(match.group(1))
                return rtt
            else:
                return None

        except Exception as e:
            return None

    def get_emulation_time(self):
        """
        Calculate current emulation time based on wall clock
        Aligns with StarryNet's emulation process

        Returns:
            Estimated emulation time in seconds (starts from 0)
        """
        if self.start_wall_time is None:
            return 0
        
        duration = time.time() - self.start_wall_time
        
        return int(duration) + 2

    def log_rtt(self, node1_index, node2_index, rtt, node1_type="sat", node2_type="sat"):
        """
        Log RTT measurement to file with both wall-clock and emulation time

        Args:
            node1_index: Index of first node
            node2_index: Index of second node
            rtt: RTT value in milliseconds
            node1_type: Type of node1 (sat/gs)
            node2_type: Type of node2 (sat/gs)
        """
        wall_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        emu_time = self.get_emulation_time()

        # Determine link type based on node types
        if node1_type == "sat" and node2_type == "sat":
            link_type = "ISL"
        elif (node1_type == "sat" and node2_type == "gs") or (node1_type == "gs" and node2_type == "sat"):
            link_type = "ISL + GSL"
        else:
            link_type = "GS-GS"

        if rtt is not None:
            log_line = f"[T={emu_time:04d}s] [{wall_time}] {link_type}: RTT({node1_type}-{node1_index}, {node2_type}-{node2_index}): {rtt:.3f} ms\n"
        else:
            log_line = f"[T={emu_time:04d}s] [{wall_time}] {link_type}: RTT({node1_type}-{node1_index}, {node2_type}-{node2_index}): FAILED\n"

        # Write to log file
        with open(self.log_file, 'a') as f:
            f.write(log_line)

    def monitor_loop(self, interval=5, node_pairs=None):
        """
        Main monitoring loop

        Args:
            interval: Monitoring interval in seconds (default: 5)
            node_pairs: List of (node1_index, node2_index, node1_type, node2_type) tuples to monitor
                       If None, monitors predefined pairs
        """
        # Default monitoring pairs if not specified
        if node_pairs is None:
            constellation_size = self.sn.constellation_size
            node_pairs = [
                (1, 2, "sat", "sat"),  # sat-to-sat
                (1, constellation_size + 1, "sat", "gs"),  # sat-to-gs
                (constellation_size + 1, constellation_size + 2, "gs", "gs"),  # gs-to-gs
            ]

        with open(self.log_file, 'a') as f:
            f.write(f"\nMonitoring started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Monitoring interval: {interval} seconds\n")
            f.write(f"Monitoring {len(node_pairs)} node pairs\n")
            f.write("-" * 80 + "\n\n")

        while self.running:
            for node1_idx, node2_idx, node1_type, node2_type in node_pairs:
                if not self.running:
                    break

                rtt = self.measure_rtt(node1_idx, node2_idx)
                self.log_rtt(node1_idx, node2_idx, rtt, node1_type, node2_type)

            # Sleep for the specified interval
            time.sleep(interval)

    def start(self, interval=5, node_pairs=None):
        """
        Start the monitoring in a background thread

        Args:
            interval: Monitoring interval in seconds (default: 5)
            node_pairs: List of node pairs to monitor
        """
        if self.running:
            print("Monitor is already running!")
            return

        # Record start time for emulation time calculation
        self.start_wall_time = time.time()

        self.running = True
        self.monitor_thread = threading.Thread(
            target=self.monitor_loop,
            args=(interval, node_pairs),
            daemon=True
        )
        self.monitor_thread.start()

    def stop(self):
        """Stop the monitoring"""
        if not self.running:
            print("Monitor is not running!")
            return

        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)

        with open(self.log_file, 'a') as f:
            f.write(f"\n\nMonitoring stopped at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n")

        print(f"Real-time monitor stopped. Log saved to {self.log_file}")


def rt_monitor(starrynet_instance, interval=5, node_pairs=None, log_file=None):
    """
    Convenience function to create and start a real-time monitor

    Args:
        starrynet_instance: The StarryNet instance to monitor
        interval: Monitoring interval in seconds (default: 5)
        node_pairs: List of (node1_index, node2_index, node1_type, node2_type) tuples to monitor
        log_file: Path to log file (default: auto-generated)

    Returns:
        RTMonitor instance (already started)
    """
    monitor = RTMonitor(starrynet_instance, log_file)
    monitor.start(interval, node_pairs)
    return monitor
