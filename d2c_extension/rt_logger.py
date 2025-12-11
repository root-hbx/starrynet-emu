#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
Real-time logging module for StarryNet
Handles all logging operations for RTT monitoring
"""

from datetime import datetime
from .doppler_calculation import format_doppler_shift


class RTLogger:
    """Logger for real-time monitoring - handles all logging operations"""

    @staticmethod
    def initialize_log(log_file):
        """
        Initialize log file with header

        Args:
            log_file: Path to log file
        """
        with open(log_file, 'w') as f:
            f.write("StarryNet Real-time Monitor Log\n")
            f.write(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

    @staticmethod
    def determine_link_type(node1_type, node2_type):
        """
        Determine link type based on node types

        Args:
            node1_type: Type of node1 (sat/gs)
            node2_type: Type of node2 (sat/gs)

        Returns:
            Link type string (ISL, ISL + GSL, or GS-GS)
        """
        if node1_type == "sat" and node2_type == "sat":
            return "ISL"
        elif (node1_type == "sat" and node2_type == "gs") or (node1_type == "gs" and node2_type == "sat"):
            return "ISL + GSL"
        else:
            return "GS-GS"

    @staticmethod
    def log_rtt(log_file, node1_index, node2_index, rtt, emu_time, node1_type="sat", node2_type="sat"):
        """
        Log RTT measurement to file with both wall-clock and emulation time

        Args:
            log_file: Path to log file
            node1_index: Index of first node
            node2_index: Index of second node
            rtt: RTT value in milliseconds (None if failed)
            emu_time: Emulation time in seconds
            node1_type: Type of node1 (sat/gs)
            node2_type: Type of node2 (sat/gs)
        """
        # wall_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
        link_type = RTLogger.determine_link_type(node1_type, node2_type)

        if rtt is not None:
            log_line = f"[T={emu_time:04d}s]\n" + f"{link_type}: RTT({node1_type}-{node1_index}, {node2_type}-{node2_index}): {rtt:.3f} ms\n"
        else:
            log_line = f"[T={emu_time:04d}s]\n" + f"{link_type}: RTT({node1_type}-{node1_index}, {node2_type}-{node2_index}): FAILED\n"

        with open(log_file, 'a') as f:
            f.write(log_line)

    @staticmethod
    def log_monitor_start(log_file, interval, num_pairs):
        """
        Log monitoring start information

        Args:
            log_file: Path to log file
            interval: Monitoring interval in seconds
            num_pairs: Number of node pairs being monitored
        """
        with open(log_file, 'a') as f:
            f.write(f"\nMonitoring started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Monitoring interval: {interval} seconds\n")
            f.write(f"Monitoring {num_pairs} node pairs\n")
            f.write("-" * 80 + "\n\n")

    @staticmethod
    def log_monitor_stop(log_file):
        """
        Log monitoring stop information

        Args:
            log_file: Path to log file
        """
        with open(log_file, 'a') as f:
            f.write(f"\n\nMonitoring stopped at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n")

    @staticmethod
    def log_gs_path(log_file, src_gs, dst_gs, src_sat, dst_sat):
        """
        Log GS-to-GS path information

        Args:
            log_file: Path to log file
            src_gs: Source GS index
            dst_gs: Destination GS index
            src_sat: Source access satellite index
            dst_sat: Destination access satellite index
        """
        if src_sat is not None and dst_sat is not None:
            path_line = f"Path: GS-{src_gs} --- SAT-{src_sat} --- ISL --- SAT-{dst_sat} --- GS-{dst_gs}\n"
        else:
            path_line = f"Path: GS-{src_gs} --- DISCONNECT --- GS-{dst_gs}\n"

        with open(log_file, 'a') as f:
            f.write(path_line)

    @staticmethod
    def log_segment_rtt(log_file, node1_index, node2_index, rtt, direction="GS-Sat", doppler_shift_hz=None):
        """
        Log GSL / ISL RTT measurement with optional Doppler shift

        Args:
            log_file: Path to log file
            gs_index: Ground station index
            sat_index: Satellite index
            rtt: RTT value in milliseconds (None if failed)
            direction: "GS-Sat" or "Sat-GS" or "Sat-Sat"
            doppler_shift_hz: Doppler shift in Hz (None if not applicable or GSL only)
        """
        if direction == "GS-Sat":
            if rtt is not None:
                log_line = f"{direction}: RTT(gs-{node1_index}, sat-{node2_index}): {rtt:.3f} ms"
                if doppler_shift_hz is not None:
                    log_line += f", Doppler Shift: {format_doppler_shift(doppler_shift_hz)}"
                log_line += "\n"
            else:
                log_line = f"{direction}: RTT(gs-{node1_index}, sat-{node2_index}): FAILED\n"
        elif direction == "Sat-GS":
            if rtt is not None:
                log_line = f"{direction}: RTT(sat-{node2_index}, gs-{node1_index}): {rtt:.3f} ms"
                if doppler_shift_hz is not None:
                    log_line += f", Doppler Shift: {format_doppler_shift(doppler_shift_hz)}"
                log_line += "\n"
            else:
                log_line = f"{direction}: RTT(sat-{node2_index}, gs-{node1_index}): FAILED\n"
        else:
            if rtt is not None:
                log_line = f"ISL: RTT(sat-{node1_index}, sat-{node2_index}): {rtt:.3f} ms\n"
            else:
                log_line = f"ISL: RTT(sat-{node1_index}, sat-{node2_index}): FAILED\n"

        with open(log_file, 'a') as f:
            f.write(log_line)
