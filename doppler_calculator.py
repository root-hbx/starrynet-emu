#!/usr/bin/python
# -*- coding: UTF-8 -*-
"""
Doppler Shift Calculator for StarryNet
Calculates Doppler shift for GSL (Ground-Satellite Links) based on TLE data
"""

import numpy as np
from sgp4.api import Satrec, WGS84
from skyfield.api import load, wgs84, EarthSatellite
from datetime import datetime


class DopplerCalculator:
    """
    Calculator for Doppler shift in satellite-ground station links
    """

    # Physical constants
    SPEED_OF_LIGHT = 299792458.0  # m/s
    EARTH_RADIUS = 6371.0  # km

    # Default carrier frequency for 5G NTN (Ku-band)
    # Reference: Wikipedia https://en.wikipedia.org/wiki/Ku_band
    DEFAULT_CARRIER_FREQ_HZ = 14.0e9  # 14 GHz (Ku-band downlink)

    def __init__(self, carrier_frequency_hz=None):
        """
        Initialize Doppler calculator

        Args:
            carrier_frequency_hz: Carrier frequency in Hz (default: 14 GHz for Ku-band)
        """
        self.carrier_freq = carrier_frequency_hz or self.DEFAULT_CARRIER_FREQ_HZ
        self.ts = load.timescale()

    def generate_satellite_from_orbital_params(self, inclination, altitude_km,
                                               mean_anomaly, raan, sat_id=0):
        """
        Generate satellite from orbital parameters (similar to sn_observer.py)

        Args:
            inclination: Inclination in degrees
            altitude_km: Altitude in kilometers
            mean_anomaly: Mean anomaly in degrees
            raan: Right ascension of ascending node in degrees
            sat_id: Satellite ID

        Returns:
            EarthSatellite object
        """
        # Convert to radians
        inclination_rad = inclination * np.pi / 180.0
        mean_anomaly_rad = mean_anomaly * np.pi / 180.0
        raan_rad = raan * np.pi / 180.0

        # Calculate mean motion
        GM = 3.9860044e14  # m^3/s^2
        R = 6371393  # m
        altitude_m = altitude_km * 1000
        mean_motion = np.sqrt(GM / (R + altitude_m)**3) * 60  # rad/min

        # Create SGP4 satellite record
        since = datetime(1949, 12, 31, 0, 0, 0)
        start = datetime(2020, 1, 1, 0, 0, 0)
        epoch = (start - since).days

        satrec = Satrec()
        satrec.sgp4init(
            WGS84,  # gravity model
            'i',  # improved mode
            sat_id,  # satellite number
            epoch,  # epoch days since 1949 Dec 31 00:00 UT
            2.8098e-05,  # bstar: drag coefficient
            6.969196665e-13,  # ndot: ballistic coefficient
            0.0,  # nddot: second derivative of mean motion
            0.001,  # ecco: eccentricity
            0.0,  # argpo: argument of perigee
            inclination_rad,  # inclo: inclination
            mean_anomaly_rad,  # mo: mean anomaly
            mean_motion,  # no_kozai: mean motion
            raan_rad,  # nodeo: RAAN
        )

        return EarthSatellite.from_satrec(satrec, self.ts)

    def calculate_radial_velocity(self, sat_position_km, sat_velocity_km_s,
                                  gs_position_km):
        """
        Calculate radial velocity (line-of-sight velocity component)

        Args:
            sat_position_km: Satellite position in GCRF [x, y, z] km
            sat_velocity_km_s: Satellite velocity in GCRF [vx, vy, vz] km/s
            gs_position_km: Ground station position in GCRF [x, y, z] km

        Returns:
            Radial velocity in m/s (positive = moving away, negative = approaching)
        """
        # Calculate relative position vector (from GS to satellite)
        rel_pos = np.array(sat_position_km) - np.array(gs_position_km)

        # Calculate distance
        distance = np.linalg.norm(rel_pos)

        if distance < 1e-6:  # Avoid division by zero
            return 0.0

        # Unit vector along line of sight
        los_unit = rel_pos / distance

        # Convert velocity to m/s
        sat_velocity_m_s = np.array(sat_velocity_km_s) * 1000.0

        # Project velocity onto line of sight
        radial_velocity = np.dot(sat_velocity_m_s, los_unit)

        return radial_velocity

    def calculate_doppler_shift(self, radial_velocity_m_s):
        """
        Calculate Doppler shift from radial velocity

        Args:
            radial_velocity_m_s: Radial velocity in m/s

        Returns:
            Doppler shift in Hz
        """
        # Doppler shift formula: f_d = (v_r / c) * f_c
        # "-" means that when the satellite is approaching (-10 -> -100), the frequency increases
        doppler_shift = -(radial_velocity_m_s / self.SPEED_OF_LIGHT) * self.carrier_freq

        return doppler_shift

    def get_satellite_state(self, satellite, time_utc):
        """
        Get satellite position and velocity at specific time

        Args:
            satellite: EarthSatellite object
            time_utc: Time as skyfield Time object

        Returns:
            Tuple of (position_km, velocity_km_s) in GCRF coordinates
        """
        # Get geocentric position
        geocentric = satellite.at(time_utc)

        # Position in km
        position_km = geocentric.position.km

        # Velocity in km/s
        velocity_km_s = geocentric.velocity.km_per_s

        return position_km, velocity_km_s

    def get_gs_position_gcrf(self, lat_deg, lon_deg, alt_m=0.0):
        """
        Get ground station position in GCRF coordinates
        # NOTE: ?

        Args:
            lat_deg: Latitude in degrees
            lon_deg: Longitude in degrees
            alt_m: Altitude in meters (default: 0)

        Returns:
            Position [x, y, z] in km in GCRF coordinates
        """
        # Create ground station location
        gs_location = wgs84.latlon(lat_deg, lon_deg, elevation_m=alt_m)

        # Get position at a reference time
        # For position only, any time works since GS is stationary in ECEF
        t = self.ts.utc(2022, 1, 1, 0, 0, 0)

        # Get geocentric position
        geocentric = gs_location.at(t)
        position_km = geocentric.position.km

        return position_km

    def calculate_doppler_for_gsl(self, satellite, gs_lat, gs_lon, time_utc,
                                   gs_alt_m=0.0):
        """
        Calculate Doppler shift for a ground-satellite link

        Args:
            satellite: EarthSatellite object
            gs_lat: Ground station latitude in degrees
            gs_lon: Ground station longitude in degrees
            time_utc: Time as skyfield Time object
            gs_alt_m: Ground station altitude in meters

        Returns:
            Tuple of (doppler_shift_hz, radial_velocity_m_s)
        """
        # Get satellite state
        sat_pos_km, sat_vel_km_s = self.get_satellite_state(satellite, time_utc)

        # Get ground station position
        gs_pos_km = self.get_gs_position_gcrf(gs_lat, gs_lon, gs_alt_m)

        # Calculate radial velocity
        radial_vel = self.calculate_radial_velocity(sat_pos_km, sat_vel_km_s, gs_pos_km)

        # Calculate Doppler shift
        doppler_shift = self.calculate_doppler_shift(radial_vel)

        return doppler_shift, radial_vel


def format_doppler_shift(doppler_hz):
    """
    Format Doppler shift for display

    Args:
        doppler_hz: Doppler shift in Hz

    Returns:
        Formatted string
    """
    if abs(doppler_hz) >= 1e6:
        return f"{doppler_hz/1e6:.3f} MHz"
    elif abs(doppler_hz) >= 1e3:
        return f"{doppler_hz/1e3:.3f} kHz"
    else:
        return f"{doppler_hz:.3f} Hz"
