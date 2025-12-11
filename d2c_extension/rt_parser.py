#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
Real-time parsing module for StarryNet
Handles parsing of network command outputs
"""

import re


class RTParser:
    """Parser for real-time monitoring - handles parsing of network command outputs"""

    @staticmethod
    def parse_ping_output(output):
        """
        Parse RTT from ping command output

        Args:
            output: String output from ping command

        Returns:
            RTT in milliseconds as float, or None if parsing failed
        """
        # Looking for pattern like "time=XX.X ms"
        match = re.search(r'time=([\d.]+)\s*ms', output)
        if match:
            return float(match.group(1))
        return None
