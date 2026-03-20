DDoS Simulation Lab with Embedded Alert System
Project Overview:

This project implements a controlled simulation environment for DDoS (Distributed Denial of Service) attacks.
The goal is to demonstrate how abnormal network traffic can be detected and visualized using an embedded hardware alert system.

The system is built as a modular pipeline:

-Traffic generation (attack simulation)
-Web server (victim)
-Monitoring and detection
-Embedded system alert (EV10P22A)

System Architecture:

Attack VM(s)
    ↓
Victim Web Server (Nginx/Apache)
    ↓
Monitoring System (Python)
    ↓
Serial Communication (USB)
    ↓
Embedded Board (EV10P22A)
    ↓
RGB LED Indicator

Explanation:
Attack virtual machines generate HTTP traffic toward a test web server.
The server logs incoming requests.
A Python monitoring script analyzes traffic (requests per second).
Based on thresholds, the system classifies traffic as:
-NORMAL
-WARNING
-ATTACK

The monitoring system sends a signal via serial communication.
The embedded device displays the system state using an RGB LED.

State	Condition	LED Color:

NORMAL	Low traffic	Green
WARNING	Increased traffic	Yellow
ATTACK	High traffic (DDoS)	Red (blinking)

Project Structure:
ddos-simulation-embedded-alert
 attack/        # Traffic generation scripts
 monitoring/    # Python scripts for detection
 victim/        # Web server configuration
 embedded/      # EV10P22A firmware
