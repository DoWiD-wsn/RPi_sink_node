import serial, time, logging
import sys, signal

##### SETTINGS #####
# Serial baud
BAUD = 9600

def signal_handler(signal, frame):
    sys.exit(0)

##### ROUTINE #####
# Parameter given
if (len(sys.argv) < 2):
    print("ERROR: the script needs the serial port as parameter!")
    print("Usage:")
    print("  python3 serial_data_logger.py PORT")
    print("Example:")
    print("  python3 serial_data_logger.py /dev/ttyUSB0")
    exit(-1)
# Use given file as input
PORT = str(sys.argv[1])
# Prepare logfilename
FILE = time.strftime("%Y-%m-%d_%H-%M-%S") + "_-_" + PORT.split("/")[-1] + ".log"

# Prepare logging module
logging.basicConfig(filename=FILE, filemode='w', format="%(asctime)s -- %(message)s", datefmt="%Y-%m-%d %H:%M:%S",level=logging.INFO)
# Install signal handler
signal.signal(signal.SIGINT, signal_handler)
# Get the serial interface
ser = serial.Serial(PORT, BAUD, timeout=None)
# Run until a signal is caught
while True:
    try:
        s = ser.readline()
        line = s.decode('utf-8').replace('\r\n','')
        line = line.strip()
        logging.info(line)
    except:
        ser.flush()
    time.sleep(1)
