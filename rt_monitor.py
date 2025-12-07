import threading
import time
import re
import os
from datetime import datetime

# Import utility functions from sn_utils
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'starrynet'))
from sn_utils import sn_ping, sn_perf, sn_route


class Parser:
    """File parser for StarryNet monitor results"""

    @staticmethod
    def parse_ping_result(result_file):
        """
        Parse ping result file to extract RTT statistics

        Args:
            result_file: Path to ping result file

        Returns:
            dict with min/avg/max/mdev RTT, or None if parsing failed
        """
        try:
            with open(result_file, 'r') as f:
                content = f.read()

            # Parse RTT statistics from ping output
            # Looking for pattern like "rtt min/avg/max/mdev = 1.234/2.345/3.456/0.123 ms"
            match = re.search(r'rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', content)
            if match:
                return {
                    'min': float(match.group(1)),
                    'avg': float(match.group(2)),
                    'max': float(match.group(3)),
                    'mdev': float(match.group(4))
                }

            # Fallback: try to find individual RTT values
            times = re.findall(r'time=([\d.]+)\s*ms', content)
            if times:
                times = [float(t) for t in times]
                return {
                    'min': min(times),
                    'avg': sum(times) / len(times),
                    'max': max(times),
                    'mdev': 0.0  # Not calculated in this case
                }

            return None
        except Exception as e:
            return None

    @staticmethod
    def parse_iperf_result(result_file):
        """
        Parse iperf3 result file to extract bandwidth information

        Args:
            result_file: Path to iperf3 result file

        Returns:
            dict with bandwidth (Mbps/Gbps) and other stats, or None if parsing failed
        """
        try:
            with open(result_file, 'r') as f:
                content = f.read()
            
            lines = content.strip().split('\n')

            for line in reversed(lines):
                # Look for receiver bandwidth (more accurate for TCP)
                if 'receiver' in line.lower():
                    # Pattern: "[ ID] Interval ... Bandwidth"
                    # Example: "[  5]   0.00-5.00   sec  1.23 GBytes  2.11 Gbits/sec    receiver"
                    match = re.search(r'([\d.]+)\s+(Mbits|Gbits)/sec', line)
                    if match:
                        bw_value = float(match.group(1))
                        bw_unit = match.group(2)

                        # Convert to Mbps for consistency
                        if bw_unit == 'Gbits':
                            bw_mbps = bw_value * 1000
                        else:
                            bw_mbps = bw_value

                        return {
                            'bandwidth_mbps': bw_mbps,
                            'bandwidth': bw_value,
                            'unit': bw_unit
                        }

            return None
        except Exception as e:
            return None


class Logger:
    """Logger for StarryNet monitor results"""

    @staticmethod
    def log_rtt(log_file, emu_time, wall_time, src_index, des_index, 
            rtt_stats, src_type="sat", des_type="sat"
    ):
        """
        Log RTT measurement to file

        Args:
            log_file: Path to log file
            emu_time: Emulation time in seconds
            wall_time: Wall clock time as string
            src_index: Index of source node
            des_index: Index of destination node
            rtt_stats: dict with RTT statistics (min/avg/max/mdev) or None if failed
            src_type: Type of source node (sat/gs)
            des_type: Type of destination node (sat/gs)
        """
        # Determine link type based on node types
        if src_type == "sat" and des_type == "sat":
            link_type = "ISL"
        elif (src_type == "sat" and des_type == "gs") or (src_type == "gs" and des_type == "sat"):
            link_type = "GSL or GSL + ISL"
        else:
            link_type = "GS-GS"

        if rtt_stats is not None:
            log_line = (
                f"[T={emu_time:04d}s] [{wall_time}] {link_type}: "
                f"RTT({src_type}-{src_index}, {des_type}-{des_index}): "
                f"{rtt_stats['avg']:.3f}"
            )
        else:
            log_line = (
                f"[T={emu_time:04d}s] [{wall_time}] {link_type}: "
                f"RTT({src_type}-{src_index}, {des_type}-{des_index}): FAILED\n"
            )

        # Write to log file
        with open(log_file, 'a') as f:
            f.write(log_line)

    @staticmethod
    def log_bw(log_file, emu_time, wall_time, src_index, des_index, bw_stats, src_type="sat", des_type="sat"):
        """
        Log bandwidth measurement to file with both wall-clock and emulation time

        Args:
            src_index: Index of source node
            des_index: Index of destination node
            bw_stats: dict with bandwidth info (bandwidth_mbps, bandwidth, unit) or None if failed
            src_type: Type of source node (sat/gs)
            des_type: Type of destination node (sat/gs)
        """
        # Determine link type based on node types
        if src_type == "sat" and des_type == "sat":
            link_type = "ISL"
        elif (src_type == "sat" and des_type == "gs") or (src_type == "gs" and des_type == "sat"):
            link_type = "GSL or GSL + ISL"
        else:
            link_type = "GS-GS"

        if bw_stats is not None:
            log_line = (
                f"[T={emu_time:04d}s] [{wall_time}] {link_type}: "
                f"BW({src_type}-{src_index}, {des_type}-{des_index}): "
                f"({bw_stats['bandwidth_mbps']:.2f} Mbps)\n"
            )
        else:
            log_line = (
                f"[T={emu_time:04d}s] [{wall_time}] {link_type}: "
                f"BW({src_type}-{src_index}, {des_type}-{des_index}): FAILED\n"
            )

        # Write to log file
        with open(log_file, 'a') as f:
            f.write(log_line)


class RTMonitor:
    """Real-time monitor for StarryNet emulation"""

    def __init__(self, starrynet_instance, log_prefix=None):
        """
        Initialize the real-time monitor

        Args:
            starrynet_instance: StarryNet instance to monitor
            log_prefix: Prefix for log files (default: ./rt_log_<timestamp>)
                       Each metric will create a separate file: {prefix}_rtt.txt, {prefix}_bw.txt, etc.
        """
        self.sn = starrynet_instance
        self.running = False
        self.monitor_thread = None
        self.emulation_time = 0  # Track emulation time in seconds
        self.start_wall_time = None  # Wall clock time when emulation starts
        self.log_files = {} # Logging file path for each metric
        
        # Generate log file prefix with timestamp if not provided
        if log_prefix is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_prefix = f"./rt_log_{timestamp}"
        else:
            self.log_prefix = log_prefix

    def measure_rtt(self, src_index, des_index):
        """
        Measure RTT between two nodes using sn_ping() from sn_utils

        Args:
            src_index: Source node index (1-based)
            des_index: Destination node index (1-based)

        Returns:
            dict with RTT statistics (min/avg/max/mdev), or None if failed
        """
        try:
            # Get current emulation time as time_index
            time_index = self.get_emulation_time()

            # Call sn_ping() to perform ping and save result to file
            sn_ping(
                src=src_index,
                des=des_index,
                time_index=time_index,
                constellation_size=self.sn.constellation_size,
                container_id_list=self.sn.container_id_list,
                file_path=self.sn.file_path,
                configuration_file_path=self.sn.configuration_file_path,
                remote_ssh=self.sn.remote_ssh
            )

            # Parse result file
            result_file = os.path.join(
                self.sn.configuration_file_path,
                self.sn.file_path,
                f"ping-{src_index}-{des_index}_{time_index}.txt"
            )

            return Parser.parse_ping_result(result_file)

        except Exception as e:
            print(f"Error measuring RTT: {e}")
            return None

    def measure_bw(self, src_index, des_index):
        """
        Measure end-to-end bandwidth between two nodes using sn_perf() from sn_utils

        Note: This measures the effective bandwidth of the entire path from src to des,
              regardless of the number of hops. The result reflects the bottleneck bandwidth.

        Args:
            src_index: Source node index (1-based)
            des_index: Destination node index (1-based)

        Returns:
            dict with bandwidth info (bandwidth_mbps, bandwidth, unit), or None if failed
        """
        try:
            # Get current emulation time as time_index
            time_index = self.get_emulation_time()

            # Call sn_perf() to perform iperf3 test and save result to file
            sn_perf(
                src=src_index,
                des=des_index,
                time_index=time_index,
                constellation_size=self.sn.constellation_size,
                container_id_list=self.sn.container_id_list,
                file_path=self.sn.file_path,
                configuration_file_path=self.sn.configuration_file_path,
                remote_ssh=self.sn.remote_ssh
            )

            # Parse result file
            result_file = os.path.join(
                self.sn.configuration_file_path,
                self.sn.file_path,
                f"perf-{src_index}-{des_index}_{time_index}.txt"
            )

            return Parser.parse_iperf_result(result_file)

        except Exception as e:
            print(f"Error measuring bandwidth: {e}")
            return None

    def measure_routing(self, node_index):
        """
        Get routing table of a specific node using sn_route() from sn_utils

        Args:
            node_index: Node index (1-based)

        Returns:
            List of routing table lines, or None if failed
        """
        try:
            # Get current emulation time as time_index
            time_index = self.get_emulation_time()

            # Call sn_route() to get routing table and save to file
            sn_route(
                src=node_index,
                time_index=time_index,
                file_path=self.sn.file_path,
                configuration_file_path=self.sn.configuration_file_path,
                container_id_list=self.sn.container_id_list,
                remote_ssh=self.sn.remote_ssh
            )

            # Read result file
            result_file = os.path.join(
                self.sn.configuration_file_path,
                self.sn.file_path,
                f"route-{node_index}_{time_index}.txt"
            )

            with open(result_file, 'r') as f:
                routes = f.readlines()

            return routes

        except Exception as e:
            print(f"Error getting routing table: {e}")
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

    def monitor_loop(self, interval=5, node_pairs=None, measure_types=None):
        """
        Main monitoring loop

        Args:
            interval: Monitoring interval in seconds (default: 5)
            node_pairs: List of (src_index, des_index, src_type, des_type) tuples to monitor
                       If None, monitors predefined pairs
            measure_types: List of measurement types to perform: 'rtt', 'bw', or both
                          Default: ['rtt']
        """
        # Default monitoring pairs if not specified
        if node_pairs is None:
            constellation_size = self.sn.constellation_size
            node_pairs = [
                (1, 2, "sat", "sat"),  # sat-to-sat
                (1, constellation_size + 1, "sat", "gs"),  # sat-to-gs
            ]

        # Default measure types
        if measure_types is None:
            measure_types = ['rtt']

        # Write monitoring info to each metric's log file
        for metric in measure_types:
            metric_name = 'bw' if metric == 'bandwidth' else metric
            if metric_name in self.log_files:
                with open(self.log_files[metric_name], 'a') as f:
                    f.write(f"\nMonitoring started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Monitoring interval: {interval} seconds\n")
                    f.write(f"Monitoring {len(node_pairs)} node pairs\n")
                    f.write("-" * 80 + "\n\n")

        while self.running:
            for src_idx, des_idx, src_type, des_type in node_pairs:
                if not self.running:
                    break

                # RTT Measurement
                if 'rtt' in measure_types:
                    rtt_stats = self.measure_rtt(src_idx, des_idx)
                    wall_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    emu_time = self.get_emulation_time()
                    Logger.log_rtt(self.log_files['rtt'], emu_time, wall_time, src_idx, des_idx, rtt_stats, src_type, des_type)

                # Bandwidth Measurement
                if 'bw' in measure_types or 'bandwidth' in measure_types:
                    bw_stats = self.measure_bw(src_idx, des_idx)
                    wall_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
                    emu_time = self.get_emulation_time()
                    Logger.log_bw(self.log_files['bw'], emu_time, wall_time, src_idx, des_idx, bw_stats, src_type, des_type)

            # Sleep for the specified interval
            time.sleep(interval)

    def start(self, interval=5, node_pairs=None, measure_types=None):
        """
        Start the monitoring in a background thread

        Args:
            interval: Monitoring interval in seconds (default: 5)
            node_pairs: List of (src_index, des_index, src_type, des_type) tuples to monitor
            measure_types: List of measurement types: 'rtt', 'bw', or both (default: ['rtt'])
        """
        if self.running:
            print("Monitor is already running!")
            return

        # Default measure types
        if measure_types is None:
            measure_types = ['rtt']

        # Initialize log files for each metric
        for metric in measure_types:
            # Normalize metric name (handle 'bandwidth' -> 'bw')
            metric_name = 'bw' if metric == 'bandwidth' else metric
            log_file = f"{self.log_prefix}_{metric_name}.txt"
            self.log_files[metric_name] = log_file

            # Create and initialize the log file
            with open(log_file, 'w') as f:
                f.write(f"StarryNet Real-time Monitor - {metric_name.upper()} Log\n")
                f.write(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n\n")

        # Record start time for emulation time calculation
        self.start_wall_time = time.time()
        self.running = True

        self.monitor_thread = threading.Thread(
            target=self.monitor_loop,
            args=(interval, node_pairs, measure_types),
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

        # Write stop message to all log files
        for metric_name, log_file in self.log_files.items():
            with open(log_file, 'a') as f:
                f.write(f"\n\nMonitoring stopped at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 80 + "\n")

        # Print summary of all log files
        if self.log_files:
            print("Real-time monitor stopped. Logs saved to:")
            for metric_name, log_file in self.log_files.items():
                print(f"  - {metric_name.upper()}: {log_file}")
        else:
            print("Real-time monitor stopped.")


def rt_monitor(starrynet_instance, interval=5, node_pairs=None,
               measure_types=None, log_prefix=None
):
    monitor = RTMonitor(starrynet_instance, log_prefix)
    monitor.start(interval, node_pairs, measure_types)
    return monitor
