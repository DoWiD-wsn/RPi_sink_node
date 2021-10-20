#####
# @brief    RPi sink node centralized DCA analysis
#
# Python script running on the RPi-based sink node (but not limited to)
# to perform a centralized DCA on the sensor measurement and
# diagnostic data collected from the sensor nodes.
# The result are the use-case specific data in combination with an
# assigned anomaly context between 0 and 1 where 0 means a "normal"
# context and 1 refers to circumstances that facilitate node faults.
# The resulting data are plotted via mathplotlib and, optionally, are
# stored in a CSV file.
#
# This is the version used in the centralized DCA WSN testbed.
#
# @file     centralized_dca_analysis.py
# @author   Dominik Widhalm
# @version  0.1.0
# @date     2021/10/20
#####


##### LIBRARIES ########################
# basic math
import math
# for date/time
from datetime import datetime
from datetime import timedelta
import time
# To connect to MySQL DB
import mysql.connector
from mysql.connector import errorcode
# CSV functionality
import csv
# for plotting
import matplotlib.pyplot as plt
plt.rcParams.update({'font.size': 12})
from matplotlib import rc
rc('mathtext', default='regular')
from matplotlib.ticker import (AutoMinorLocator, MultipleLocator)
import matplotlib.dates as md


##### GLOBAL VARIABLES #####
# dendritic cell lifetime/population
DC_N        = 5

# Period to analyze
p_start     = "2021-10-19 17:00:00"
p_end       = "2021-10-20 11:00:00"

# Sensor node ID (use single nodes for now)
nodes       = "41B9FD22"
#nodes       = ["41B9F864","41B9F805","41B9FFC2","41B9FFD8","41B9FFDD","41B9FD22","41BA26F1","41CC57CC","41CC3F83","41CC3E8F","41CC5591"]

# CSV output (0...disable/1...enable)
CSV_OUTPUT  = 1

# DB CONNECTION
DB_CON_HOST = "192.168.13.98"
DB_CON_USER = "mywsn"
DB_CON_PASS = "$MyWSNdemo$"
DB_CON_BASE = "wsn_testbed"

# Date/time format
fmt         = '%Y-%m-%d %H:%M:%S'
xfmt        = md.DateFormatter('%H:%M')


##### METHODS #####################
# See https://www.codegrepper.com/code-examples/python/python+datetime+round+to+nearest+hour
def hour_rounder(t):
    # Rounds to nearest hour by adding a timedelta hour if minute >= 30
    return (t.replace(second=0, microsecond=0, minute=0, hour=t.hour)
               +timedelta(hours=t.minute//30))


###################################
##### Step 0 - initialization #####
###################################

# Choose ID/antigen
SNID = nodes
# Period (in UTC)
start_utc = datetime.strptime(p_start,fmt) + timedelta(hours = -2)
start_utc_str = start_utc.strftime(fmt)
end_utc = datetime.strptime(p_end,fmt) + timedelta(hours = -2)
end_utc_str = end_utc.strftime(fmt)

# Try to connect to the database
db_con = None
db_cur = None
try:
    db_con = mysql.connector.connect(host=DB_CON_HOST, user=DB_CON_USER, password=DB_CON_PASS, database=DB_CON_BASE)
except Exception as e:
    print("Connection to the DB failed!")
    print(e)
    exit(-1)
else:
    # Check if DB is really connected
    if db_con.is_connected():
        # Get an cursor for the DB
        db_cur = db_con.cursor()
    else:
        print("Connecting worked by connection is not open!")
        exit(-1)

# Prepare CSV file (if needed)
if CSV_OUTPUT:
    CSV_FILE = "centralized_dca-%s-output.csv" % SNID
    # Try to open/create CSV file
    csv_o = None
    try:
        # Open CSV file
        csv_f = open(CSV_FILE, 'w')
        # Get a CSV writer
        csv_o = csv.writer(csv_f)
    except Exception as e:
        print("Cannot open the CSV file/reader ... aborting!")
        print(e)
        exit(-1)
    # Write initial rows into the CSV file
    try:
        csv_o.writerow(["snid [lower 32-bit of MAC]", "time [UNIX]", "T_air [°C]", "T_soil [°C]", "H_air [%RH]", "H_soil [%RH]", "x_nt",  "x_vs",  "x_bat",  "x_art",  "x_rst",  "x_ic",  "x_adc",  "x_usart",  "PAMP",  "danger",  "safe", "context [0..1]"])
    except Exception as e:
        print("Writing initial data to the CSV file failed ... aborting!")
        print(e)
        exit(-1)

# Prepare query string
query = "SELECT * FROM `sensordata` WHERE `snid` LIKE '" + SNID + "' AND (`dbtime` BETWEEN '" + start_utc_str + "' AND '" + end_utc_str + "') ORDER BY `id` ASC"
# Execute query
try:
    db_cur.execute(query)
    entries = db_cur.fetchall()
except Exception as e:
    print("Querying/fetching DB data didn't work ... aborting!")
    print(e)
    exit(-1)
# Check number of rows fetched
if len(entries)<1:
    print("There was no data to process ... aborting!")
    exit(-1)

# Prepare data arrays/lists/etc.
snid        = []
sntime      = []
time        = []
tstmp       = []
# use case data
t_air       = []
t_soil      = []
h_air       = []
h_soil      = []
# fault indicator
x_nt        = []
x_vs        = []
x_bat       = []
x_art       = []
x_rst       = []
x_ic        = []
x_adc       = []
x_usart     = []
# DCA signals
PAMP        = []
danger      = []
safe        = []
# Anomaly context
context     = []
# DCA internals ... initially, there are no DCs -> empty lists
dcs         = []


#######################################
##### Step 1 - sensor node update #####
#######################################

# Iterate over entries
for row in entries:
    ### GENERAL ###
    # Get snid
    snid.append(str(row[1]))
    # Get sntime
    sntime.append(int(row[2]))
    # Get datetime from row
    dtime = datetime.strptime(str(row[3]), fmt) + timedelta(hours = 2)
    # Add datetime to time array
    time.append(dtime)
    # Convert datetime to UNIX timestamp
    tstmp.append(int(datetime.timestamp(dtime)))
    
    ### USE CASE DATA ###
    # Get sensor readings
    t_air.append(round(float(row[4]),2))
    t_soil.append(round(float(row[5]),2))
    h_air.append(round(float(row[6]),2))
    h_soil.append(round(float(row[7]),2))
    
    ### FAULT INDICATOR ###
    # Get indicator values
    x_nt.append(round(float(row[8]),2))
    x_vs.append(round(float(row[9]),2))
    x_bat.append(round(float(row[10]),2))
    x_art.append(round(float(row[11]),2))
    x_rst.append(round(float(row[12]),2))
    x_ic.append(round(float(row[13]),2))
    x_adc.append(round(float(row[14]),2))
    x_usart.append(round(float(row[15]),2))
    
    
##################################
##### Step 2 - signal update #####
##################################


##########################################
##### Step 3 - dendritic cell update #####
##########################################


#######################################
##### Step 4 - context assignment #####
#######################################


####################################
##### Step 1.2 - result output #####
####################################

### Close database connection
if db_con.is_connected():
    db_cur.close()
    db_con.close()

### Save data to CSV file if required
if CSV_OUTPUT:
    # Iterate over all data
    for i in range(0,len(time)):
        try:
            # Write a row to the CSV file
            csv_o.writerow([snid[i], time[i], t_air[i], t_soil[i], h_air[i], h_soil[i], x_nt[i], x_vs[i], x_bat[i], x_art[i], x_rst[i], x_ic[i], x_adc[i], x_usart[i], PAMP[i], danger[i], safe[i], context[i]])
        except Exception as e:
            print("Writing measurement data to the CSV file failed ... aborting!")
            print(e)
            exit(-1)
    # Close CSV file
    try:
        # Try to close the CSV file
        csv_f.close()
    except Exception as e:
        print("Couldn't close CSV file ... aborting!")
        print(e)

### Plot the data via matplotlib
# get lowest (first) and highest (last) time
x_first = hour_rounder(time[0])
x_last  = hour_rounder(time[-1])

# prepare figure
fig = plt.figure(figsize=(12,5), dpi=150, tight_layout=True)
ax1 = fig.add_subplot(211)
ax1b = ax1.twinx()
ax2 = fig.add_subplot(212)

## temperature/humidity plot
# grid
ax1.grid(which='major', color='#CCCCCC', linestyle=':')
# x-axis
ax1.xaxis.set_major_locator(md.HourLocator(interval = 12))
ax1.xaxis.set_minor_locator(AutoMinorLocator(2))
ax1.set_xticklabels([])
ax1b.set_xticklabels([])
# y-axis
ax1.set_ylabel(r"temperature [$^{\circ}$C]")
ax1.set_xlim(x_first,x_last)
ax1.set_ylim(0,40)
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)
ax1.yaxis.set_major_locator(MultipleLocator(10))
ax1.yaxis.set_minor_locator(AutoMinorLocator(2))
ax1b.set_xlim(x_first,x_last)
ax1b.set_ylabel("relative humidity [%]")
ax1b.set_ylim(0,100)
ax1b.spines['top'].set_visible(False)
ax1b.spines['left'].set_visible(False)
ax1b.xaxis.set_ticks_position('bottom')
ax1b.spines['bottom'].set_position(('data',0))
ax1b.yaxis.set_ticks_position('right')
ax1b.yaxis.set_major_locator(MultipleLocator(25))
ax1b.yaxis.set_minor_locator(AutoMinorLocator(2))
# plot data
lns1 = ax1.plot(time, t_air, '-',  label=r"$T_{air}$", linewidth=2, color="darkgreen")
lns2 = ax1.plot(time, t_soil, '-',  label=r"$T_{soil}$", linewidth=2, color="limegreen")
lns3 = ax1b.plot(time, h_air, '-',  label=r"$H_{air}$", linewidth=2, color="darkblue")
lns4 = ax1b.plot(time, h_soil, '-',  label=r"$H_{soil}$", linewidth=2, color="dodgerblue")
lns = lns1+lns2+lns3+lns4
labs = [l.get_label() for l in lns]
ax1b.legend(lns, labs, loc='upper right', facecolor='white', framealpha=1)

## indicator plot
# grid
ax2.grid(which='major', color='#CCCCCC', linestyle=':')
# x-axis
ax2.set_xlabel('time [H:M]')
ax2.xaxis.set_major_formatter(xfmt)
# y-axis
ax2.set_ylabel("fault indicators")
ax2.set_xlim(x_first,x_last)
ax2.set_ylim(0,1.8)
ax2.yaxis.set_major_locator(MultipleLocator(0.3))
ax2.yaxis.set_minor_locator(AutoMinorLocator(1))
ax2.set_yticklabels([])
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
# plot data
ax2.plot(time, x_nt, '-',  label=r"$\chi_{NT}$", linewidth=2, color="red")
ax2.plot(time, x_vs, '-',  label=r"$\chi_{VS}$", linewidth=2, color="darkred")
ax2.plot(time, x_bat, '-',  label=r"$\chi_{BAT}$", linewidth=2, color="slateblue")
ax2.plot(time, x_art, '-',  label=r"$\chi_{ART}$", linewidth=2, color="magenta")
ax2.plot(time, x_rst, '-',  label=r"$\chi_{RST}$", linewidth=2, color="chocolate")
ax2.plot(time, x_ic, '-',  label=r"$\chi_{IC}$", linewidth=2, color="darkviolet")
ax2.plot(time, x_adc, '-',  label=r"$\chi_{ADC}$", linewidth=2, color="darkorange")
ax2.plot(time, x_usart, '-',  label=r"$\chi_{USART}$", linewidth=2, color="darkviolet")
ax2.legend(loc='upper right', facecolor='white', framealpha=1)

### Finish figure
plt.savefig(PLOT_FILE, transparent=True)
plt.cla()
plt.clf()
plt.close()
