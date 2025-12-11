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
from .doppler_calculation import DopplerCalculator
from .rt_logger import RTLogger
from .rt_parser import RTParser


class RTMonitor:
    """Real-time monitor for StarryNet emulation"""

    def __init__(self, starrynet_instance, log_dir=".", carrier_frequency_hz=None):
        """
        Initialize the real-time monitor

        Args:
            starrynet_instance: StarryNet instance to monitor
            log_dir: Directory for log files (default: current directory)
            carrier_frequency_hz: Carrier frequency for Doppler calculation (default: 14 GHz)
        """
        self.sn = starrynet_instance
        self.running = False
        self.monitor_thread = None
        self.emulation_time = 0  # Track emulation time in seconds
        self.start_wall_time = None  # Wall clock time when emulation starts

        # Store log directory
        self.log_dir = log_dir

        # Dictionary to store log file paths for each node pair
        self.log_files_dict = {}

        # Store timestamp for generating log file names
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Initialize Doppler calculator
        self.doppler_calc = DopplerCalculator(carrier_frequency_hz)

        # Generate satellite objects for Doppler calculation
        self.satellites = self._generate_satellites()

        # Store GS locations from StarryNet instance
        self.gs_locations = self.sn.observer.GS_lat_long

    def _generate_satellites(self):
        """
        Generate satellite objects for all satellites in the constellation
        Aligns with the constellation generation in sn_observer.py

        Returns:
            List of EarthSatellite objects
        """
        satellites = []

        # Get constellation parameters from StarryNet instance
        orbit_num = self.sn.orbit_number
        sat_num = self.sn.sat_number
        inclination = self.sn.inclination
        altitude_km = self.sn.satellite_altitude

        # Phase shift parameter (align with F in sn_observer.py)
        F = 18
        num_of_sat = orbit_num * sat_num

        # Generate satellites using same logic as sn_observer.py
        for i in range(orbit_num):
            raan = i / orbit_num * 360
            for j in range(sat_num):
                mean_anomaly = (j * 360 / sat_num + i * 360 * F / num_of_sat) % 360
                satellite = self.doppler_calc.generate_satellite_from_orbital_params(
                    inclination=inclination,
                    altitude_km=altitude_km,
                    mean_anomaly=mean_anomaly,
                    raan=raan,
                    sat_id=i * sat_num + j
                )
                satellites.append(satellite)

        return satellites

    def calculate_doppler_shift_for_gsl(self, gs_index, sat_index):
        """
        Calculate Doppler shift for a ground-satellite link

        Args:
            gs_index: Ground station index (1-based, > constellation_size)
            sat_index: Satellite index (1-based, <= constellation_size)

        Returns:
            Doppler shift in Hz, or None if calculation failed
        """
        try:
            # Convert to 0-based indices
            sat_idx = sat_index - 1
            gs_idx = gs_index - self.sn.constellation_size - 1

            # Check if satellite and GS indices are valid
            if sat_idx < 0 or sat_idx >= len(self.satellites):
                return None
            if gs_idx < 0 or gs_idx >= len(self.gs_locations):
                return None

            # Get satellite object
            satellite = self.satellites[sat_idx]

            # Get GS location
            gs_lat, gs_lon = self.gs_locations[gs_idx]

            # Get current time for Doppler calculation
            # Use emulation time aligned with StarryNet's time
            # NOTE: Key part to showcase "time fluctuation" traits
            # if self.get_emulation_time() = 5 s,
            # then we set time to 2022-01-01 01:00:05 UTC
            current_time = self.doppler_calc.ts.utc(2022, 1, 1, 1, 0, self.get_emulation_time())

            # Calculate Doppler shift
            doppler_hz, _ = self.doppler_calc.calculate_doppler_for_gsl(
                satellite, gs_lat, gs_lon, current_time
            )

            return doppler_hz

        except Exception:
            return None

    def measure_rtt(self, node1_index, node2_index, retries=3, timeout=3):
        """
        Measure RTT between two nodes using ping with retry logic

        Args:
            node1_index: Index of first node
            node2_index: Index of second node
            retries: Number of ping packets to send (default: 3)
            timeout: Timeout in seconds per packet (default: 3)

        Returns:
            RTT in milliseconds, or None if ping failed
        """
        try:
            # Get IP address of node2
            ip_list = self.sn.get_IP(node2_index)
            if not ip_list or len(ip_list) == 0:
                return None

            target_ip = ip_list[0]

            # Ping: node1 to node2. Send multiple packets with longer timeout
            # -c: count (number of packets)
            # -W: timeout per packet in seconds
            # -i: interval between packets (0.2s for faster completion)
            container_id = self.sn.container_id_list[node1_index - 1]
            cmd = f"docker exec {container_id} ping -c {retries} -W {timeout} -i 0.2 {target_ip}"

            result = self.sn.remote_ssh.exec_command(cmd, get_pty=True)
            stdin, stdout, stderr = result
            output = stdout.read().decode('utf-8')

            # Parse RTT from ping output using RTParser
            # This will get the RTT from the first successful packet
            return RTParser.parse_ping_output(output)

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

    def traceroute_path(self, src_index, dst_index):
        """
        Use traceroute to get the actual routing path between two nodes

        Args:
            src_index: Index of source node
            dst_index: Index of destination node

        Returns:
            List of IP addresses in the path, or None if failed
        """
        try:
            # Get IP address of destination
            ip_list = self.sn.get_IP(dst_index)
            if not ip_list or len(ip_list) == 0:
                return None

            target_ip = ip_list[0]

            # Run traceroute from src to dst
            container_id = self.sn.container_id_list[src_index - 1]
            cmd = f"docker exec {container_id} traceroute -n -m 10 -w 3 {target_ip}"

            result = self.sn.remote_ssh.exec_command(cmd, get_pty=True)
            stdin, stdout, stderr = result
            output = stdout.read().decode('utf-8')

            # Parse traceroute output to extract IP addresses
            path_ips = []
            for line in output.split('\n'):
                # Look for lines with hop numbers and IP addresses
                # Format: " 1  10.1.2.30  0.123 ms"
                match = re.search(r'\s+\d+\s+(\d+\.\d+\.\d+\.\d+)', line)
                if match:
                    path_ips.append(match.group(1))

            return path_ips if path_ips else None

        except Exception:
            return None

    def ip_to_node_index(self, ip_address):
        """
        Convert IP address to node index by parsing the IP directly

        IP allocation rules in StarryNet:
        - GSL: 9.x.y.z where z=50 (satellite) or z=60 (GS)
          - For 9.x.y.50: satellite node = y
          - For 9.x.y.60: GS node = x + constellation_size
        - ISL: 10.x.y.z (satellite-to-satellite links)
          - Need to parse based on ISL structure

        Args:
            ip_address: IP address string

        Returns:
            Node index, or None if not found
        """
        try:
            parts = ip_address.split('.')
            if len(parts) != 4:
                return None

            first_octet = int(parts[0])
            second_octet = int(parts[1])
            third_octet = int(parts[2])
            fourth_octet = int(parts[3])

            constellation_size = self.sn.constellation_size

            # GSL IP: 9.x.y.z
            if first_octet == 9:
                if fourth_octet == 50:
                    # Satellite side of GSL: node = y (third octet)
                    return third_octet
                elif fourth_octet == 60:
                    # GS side of GSL: GS node = x + constellation_size
                    return second_octet + constellation_size

            # ISL IP: 10.x.y.z
            # For ISL, we need to extract satellite ID from the structure
            # Based on ISL addressing: isl_idx is encoded in octets 2 and 3
            elif first_octet == 10:
                # ISL index is encoded in second and third octets
                isl_idx = (second_octet << 8) | third_octet
                # Each satellite has 2 ISLs (intra and inter-orbit)
                satellite_id = (isl_idx - 1) // 2 + 1
                if satellite_id <= constellation_size:
                    return satellite_id

            return None

        except Exception:
            return None

    def get_gs_access_sat_from_route(self, src_gs, dst_gs):
        """
        Get the actual access satellites used in routing from src_gs to dst_gs

        Args:
            src_gs: Source ground station index
            dst_gs: Destination ground station index

        Returns:
            Tuple of (src_access_sat, dst_access_sat), or (None, None) if failed
        """
        try:
            # Get the actual routing path using traceroute
            path_ips = self.traceroute_path(src_gs, dst_gs)

            if not path_ips or len(path_ips) < 2:
                return None, None

            constellation_size = self.sn.constellation_size

            # First hop from src_gs should be the source access satellite
            src_sat = None
            for ip in path_ips[:3]:  # Check first few hops
                node_idx = self.ip_to_node_index(ip)
                if node_idx and node_idx <= constellation_size:
                    src_sat = node_idx
                    break

            # Last hop before dst_gs should be the destination access satellite
            dst_sat = None
            for ip in reversed(path_ips[-3:]):  # Check last few hops
                node_idx = self.ip_to_node_index(ip)
                if node_idx and node_idx <= constellation_size:
                    dst_sat = node_idx
                    break

            return src_sat, dst_sat

        except Exception:
            return None, None

    def log_rtt(self, log_file, node1_index, node2_index, rtt, node1_type="sat", node2_type="sat"):
        """
        Log RTT measurement to file with both wall-clock and emulation time

        Args:
            log_file: Path to log file for this node pair
            node1_index: Index of first node
            node2_index: Index of second node
            rtt: RTT value in milliseconds
            node1_type: Type of node1 (sat/gs)
            node2_type: Type of node2 (sat/gs)
        """
        emu_time = self.get_emulation_time()

        # If GS-to-GS, log path segments and accumulated RTT
        if node1_type == "gs" and node2_type == "gs":
            # Log timestamp first
            RTLogger.log_timestamp(log_file, emu_time)

            # IMPORTANT: Get path first, then immediately measure all segments
            # to minimize timing window issues in dynamic LEO networks
            src_sat, dst_sat = self.get_gs_access_sat_from_route(node1_index, node2_index)
            RTLogger.log_gs_path(log_file, node1_index, node2_index, src_sat, dst_sat)

            # Fast sequential measurement of all segments to reduce timing window
            # Use retries=3 and timeout=3 to handle packet loss and transient issues

            # Initialize segment RTTs
            gs_sat_rtt = None
            sat_gs_rtt = None
            sat_sat_rtt = None

            # Measure and log GS-Sat (GSL) RTT with Doppler shift
            if src_sat is not None:
                gs_sat_rtt = self.measure_rtt(node1_index, src_sat, retries=3, timeout=3)
                # Calculate Doppler shift for GS-Sat link
                doppler_shift = self.calculate_doppler_shift_for_gsl(node1_index, src_sat)
                RTLogger.log_segment_rtt(log_file, node1_index, src_sat, gs_sat_rtt,
                                        "GS-Sat", doppler_shift_hz=doppler_shift)

            if dst_sat is not None:
                sat_gs_rtt = self.measure_rtt(node2_index, dst_sat, retries=3, timeout=3)
                # Calculate Doppler shift for Sat-GS link
                doppler_shift = self.calculate_doppler_shift_for_gsl(node2_index, dst_sat)
                RTLogger.log_segment_rtt(log_file, node2_index, dst_sat, sat_gs_rtt,
                                        "Sat-GS", doppler_shift_hz=doppler_shift)

            # Measure and log Sat-Sat (ISL) RTT
            if src_sat is not None and dst_sat is not None:
                sat_sat_rtt = self.measure_rtt(src_sat, dst_sat, retries=3, timeout=3)
                RTLogger.log_segment_rtt(log_file, src_sat, dst_sat, sat_sat_rtt, "Sat-Sat")

            # Calculate and log accumulated GS-GS RTT from segments
            # Only when all segments are available can we calculate total RTT
            # else, log as FAILED
            total_rtt = None
            if gs_sat_rtt is not None and sat_gs_rtt is not None and sat_sat_rtt is not None:
                total_rtt = gs_sat_rtt + sat_gs_rtt + sat_sat_rtt

            RTLogger.log_gs_gs_accumulated_rtt(log_file, node1_index, node2_index, total_rtt)
        else:
            # For non-GS-to-GS links (sat-sat, sat-gs), use original logic
            RTLogger.log_rtt(log_file, node1_index, node2_index, rtt, emu_time, node1_type, node2_type)

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
                (1, 2, "sat", "sat"),  # sat-sat
                (1, constellation_size + 1, "sat", "gs"),  # sat-gs
                (constellation_size + 1, constellation_size + 2, "gs", "gs"),  # gs-gs
            ]

        # Log monitoring start for each pair
        for pair_key in self.log_files_dict:
            log_file = self.log_files_dict[pair_key]
            RTLogger.log_monitor_start(log_file, interval, 1)  # 1 pair per log file

        while self.running:
            for node1_idx, node2_idx, node1_type, node2_type in node_pairs:
                if not self.running:
                    break

                # Get the log file for this pair
                pair_key = (node1_idx, node2_idx, node1_type, node2_type)
                log_file = self.log_files_dict.get(pair_key)

                if log_file:
                    rtt = self.measure_rtt(node1_idx, node2_idx)
                    self.log_rtt(log_file, node1_idx, node2_idx, rtt, node1_type, node2_type)

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

        # Default monitoring pairs if not specified
        if node_pairs is None:
            constellation_size = self.sn.constellation_size
            node_pairs = [
                (1, 2, "sat", "sat"),  # sat-sat
                (1, constellation_size + 1, "sat", "gs"),  # sat-gs
                (constellation_size + 1, constellation_size + 2, "gs", "gs"),  # gs-gs
            ]

        # Create log files for each node pair
        for node1_idx, node2_idx, node1_type, node2_type in node_pairs:
            # Generate log file name based on node types and indices
            log_filename = f"rt_log_{self.timestamp}_{node1_type}-{node1_idx}_{node2_type}-{node2_idx}.txt"
            log_filepath = f"{self.log_dir}/{log_filename}"

            # Store log file path in dictionary
            pair_key = (node1_idx, node2_idx, node1_type, node2_type)
            self.log_files_dict[pair_key] = log_filepath

            # Initialize log file
            RTLogger.initialize_log(log_filepath)

        # Record start time for emulation time calculation
        self.start_wall_time = time.time()

        self.running = True
        self.monitor_thread = threading.Thread(
            target=self.monitor_loop,
            args=(interval, node_pairs),
            daemon=True
        )
        self.monitor_thread.start()

        # Print info about created log files
        print(f"Real-time monitor started with {len(node_pairs)} monitoring pairs:")
        for pair_key, log_file in self.log_files_dict.items():
            node1_idx, node2_idx, node1_type, node2_type = pair_key
            print(f"  - {node1_type}-{node1_idx} <-> {node2_type}-{node2_idx}: {log_file}")

    def stop(self):
        """Stop the monitoring"""
        if not self.running:
            print("Monitor is not running!")
            return

        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=10)

        # Log monitoring stop for each log file
        for pair_key, log_file in self.log_files_dict.items():
            RTLogger.log_monitor_stop(log_file)

        print(f"Real-time monitor stopped. Logs saved:")
        for pair_key, log_file in self.log_files_dict.items():
            node1_idx, node2_idx, node1_type, node2_type = pair_key
            print(f"  - {node1_type}-{node1_idx} <-> {node2_type}-{node2_idx}: {log_file}")


def rt_monitor(starrynet_instance, interval=5, node_pairs=None, log_dir=".", carrier_frequency_hz=None):
    """
    Convenience function to create and start a real-time monitor

    Args:
        starrynet_instance: The StarryNet instance to monitor
        interval: Monitoring interval in seconds (default: 5)
        node_pairs: List of (node1_index, node2_index, node1_type, node2_type) tuples to monitor
        log_dir: Directory for log files (default: current directory)
        carrier_frequency_hz: Carrier frequency for Doppler calculation

    Returns:
        RTMonitor instance (already started)
    """
    monitor = RTMonitor(starrynet_instance, log_dir, carrier_frequency_hz)
    monitor.start(interval, node_pairs)
    return monitor
