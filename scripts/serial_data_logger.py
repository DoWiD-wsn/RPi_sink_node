import serial, time, logging
import sys, signal

##### SETTINGS #####
# Serial port
PORT = '/dev/ttyUSB0'
# Serial baud
BAUD = 9600

def signal_handler(signal, frame):
    sys.exit(0)

# Prepare logging module
logging.basicConfig(filename="serial_data.log", filemode='a', format="%(asctime)s -- %(message)s", datefmt="%Y-%m-%d %H:%M:%S",level=logging.INFO)
# Install signal handler
signal.signal(signal.SIGINT, signal_handler)

ser = serial.Serial(PORT, BAUD, timeout=None)

while True:
    try:
        s = ser.readline()
        line = s.decode('utf-8').replace('\r\n','')
        line = line.strip()
        logging.info(line)
    except:
        ser.flush()
    time.sleep(1)
