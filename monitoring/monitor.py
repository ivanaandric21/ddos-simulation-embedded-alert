import time
import serial
import requests

SERIAL_PORT = '/dev/ttyACM0'
BAUD_RATE = 115200

def check_victim():
    try:
        start = time.time()
        r = requests.get('http://victim:80/', timeout=1)
        return time.time() - start
    except requests.exceptions.Timeout:
        return 999
    except Exception:
        return 999

def main():
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"[monitor] Connected to {SERIAL_PORT}", flush=True)
    except Exception as e:
        print(f"[monitor] Serial error: {e}", flush=True)
        ser = None

    while True:
        response_time = check_victim()
        print(f"[monitor] Response time: {response_time:.3f}s", flush=True)

        if response_time > 0.5:
            state = 'A'
        elif response_time > 0.05:
            state = 'W'
        else:
            state = 'N'

        print(f"[monitor] State: {state}", flush=True)

        if ser:
            ser.write(state.encode())

        time.sleep(2)

if __name__ == '__main__':
    main()
