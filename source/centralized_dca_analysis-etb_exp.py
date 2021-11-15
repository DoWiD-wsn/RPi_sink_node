#####
# @brief    RPi sink node centralized DCA analysis of recordings
#
# Python script running to perform a centralized DCA on the sensor 
# measurement and diagnostic data collected and recorded from the sensor
# nodes during ETB-based experiments.
# The result are the use-case specific data in combination with an
# assigned anomaly context between 0 and 1 where 0 means a "normal"
# context and 1 refers to circumstances that facilitate node faults.
# The resulting data are plotted via mathplotlib and, optionally, are
# stored in a CSV file.
#
# This is the version used in the centralized DCA ETB experiments.
#
# @file     centralized_dca_analysis-etb_exp.py
# @author   Dominik Widhalm
# @version  0.1.1
# @date     2021/11/15
#####


##### LIBRARIES ########################
# basic math
import math
# for date/time
from datetime import datetime
import time
# CSV functionality
import csv
# To get filename without path and extension
from pathlib import Path
# To handle the command line parameter
import sys
# for plotting
import matplotlib.pyplot as plt
plt.rcParams.update({'font.size': 12})
from matplotlib import rc
rc('mathtext', default='regular')
from matplotlib.ticker import (AutoLocator, AutoMinorLocator, MultipleLocator)
import matplotlib.dates as md


##### GLOBAL VARIABLES #####
# dendritic cell lifetime/population
DC_N            = 5
# number of sensor values for std-dev evaluation
STDDEV_N        = 10
# sensitivity of safe indicator
SAFE_SENS       = 0.35

# CSV output (0...disable/1...enable)
CSV_OUTPUT      = 1

# Date/time format
fmt             = '%Y-%m-%d %H:%M:%S.%f'
xfmt            = md.DateFormatter('%H:%M\n%m/%d')


##### METHODS #####################
# See https://www.codegrepper.com/code-examples/python/python+datetime+round+to+nearest+hour
def hour_rounder(t):
    # Rounds to nearest hour by adding a timedelta hour if minute >= 30
    return (t.replace(second=0, microsecond=0, minute=0, hour=t.hour)
               +timedelta(hours=t.minute//30))


###################################
##### Step 0 - initialization #####
###################################

##### Check input file ######
# Paremeter given
if (len(sys.argv) != 2):
    print("ERROR: the script needs the input CSV file as parameter!")
    exit(-1)
# Correct extension
if not (str(sys.argv[1]).endswith('.csv') or str(sys.argv[1]).endswith('.CSV')):
    print("ERROR: CSV file expected as input!")
    exit(-1)
# Use given file as input
CSV_INPUT = str(sys.argv[1])


##### GET DATA FROM CSV FILE ######
csv_i = None
try:
    # Open CSV input file
    csv_f1 = open(CSV_INPUT, 'r')
    # Get a CSV reader
    csv_i = csv.reader(csv_f1, delimiter=',')
except Exception as e:
    print("Cannot open the CSV input file \"%s\" ... aborting!" % CSV_INPUT)
    exit(-1)

# Prepare CSV output file (if needed)
if CSV_OUTPUT:
    CSV_FILE = Path(CSV_INPUT).stem + "-cdca.csv"
    # Try to open/create CSV file
    csv_o = None
    try:
        # Open CSV file
        csv_f2 = open(CSV_FILE, 'w')
        # Get a CSV writer
        csv_o = csv.writer(csv_f2)
    except Exception as e:
        print("Cannot open the CSV output file/reader ... aborting!")
        print(e)
        exit(-1)
    # Write initial rows into the CSV file
    try:
        csv_o.writerow(["snid [lower 32-bit of MAC]", "time [UNIX]", "T_air [°C]", "T_soil [°C]", "H_air [%RH]", "H_soil [%RH]", "x_nt",  "x_vs",  "x_bat",  "x_art",  "x_rst",  "x_ic",  "x_adc",  "x_usart", "antigen",  "danger",  "safe", "context [0..1]"])
    except Exception as e:
        print("Writing initial data to the CSV file failed ... aborting!")
        print(e)
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
t_air_a     = []
t_soil_a    = []
h_air_a     = []
h_soil_a    = []
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
antigen     = []
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
line_count = 0
for row in csv_i:
    if line_count>0:
        ### AUXILIARY DATA ###
        success = int(row[15])
        # Check if transmission was a success; else continue
        if not success:
            continue
        
        supply = round(float(row[16]))
        t_surface = round(float(row[17]))
        t_board = round(float(row[18]))
        t_ambient = round(float(row[19]))
        
        ### GENERAL ###
        # Get snid
        snid_t = str(row[0])
        snid.append(snid_t)
        # Get sntime
        sntime_t = int(row[1])
        sntime.append(sntime_t)
        # Get datetime from row
        dtime_t = datetime.strptime(str(row[2]), fmt)
        # Add datetime to time array
        time.append(dtime_t)
        # Convert datetime to UNIX timestamp
        tstmp.append(int(datetime.timestamp(dtime_t)))
        
        ### USE CASE DATA ###
        # Get sensor readings
        t_air_t = round(float(row[3]),2)
        t_air.append(t_air_t)
        #t_soil_t = round(float(row[4]),2)
        t_soil_t = 0
        t_soil.append(t_soil_t)
        h_air_t = round(float(row[5]),2)
        h_air.append(h_air_t)
        h_soil_t = round(float(row[6]),2)
        h_soil.append(h_soil_t)
        # Store last N sensor values
        t_air_a.append(t_air_t)
        if len(t_air_a)>STDDEV_N:
            t_air_a.pop(0)
        t_soil_a.append(t_soil_t)
        if len(t_soil_a)>STDDEV_N:
            t_soil_a.pop(0)
        h_air_a.append(h_air_t)
        if len(h_air_a)>STDDEV_N:
            h_air_a.pop(0)
        h_soil_a.append(h_soil_t)
        if len(h_soil_a)>STDDEV_N:
            h_soil_a.pop(0)
        
        ### FAULT INDICATOR ###
        # Get indicator values
        x_nt_t = round(float(row[7]),2)
        x_nt.append(x_nt_t)
        x_vs_t = round(float(row[8]),2)
        x_vs.append(x_vs_t)
        x_bat_t = round(float(row[9]),2)
        x_bat.append(x_bat_t)
        x_art_t = round(float(row[10]),2)
        x_art.append(x_art_t)
        x_rst_t = round(float(row[11]),2)
        x_rst.append(x_rst_t)
        x_ic_t = round(float(row[12]),2)
        x_ic.append(x_ic_t)
        x_adc_t = round(float(row[13]),2)
        x_adc.append(x_adc_t)
        x_usart_t = round(float(row[14]),2)
        x_usart.append(x_usart_t)


##################################
##### Step 2 - signal update #####
##################################
    
        ### ANTIGEN ###
        # use SNID as antigen
        antigen_t = snid[-1]
        # comment: does not allow spatial correlation of several nodes
        
        ## or
        
        # use combine hex fixed-point sensor values
        # antigen_t = "%04X%04X%04X%04X" % (float_to_fixed16_10to6(t_air_t),float_to_fixed16_10to6(t_soil_t),float_to_fixed16_10to6(h_air_t),float_to_fixed16_10to6(h_soil_t))
        # comment: maybe quantize to correlate values that are close to each other?
        
        # Store antigen
        antigen.append(antigen_t)
        
        ### DANGER ###
        # Use X_NT as danger1
        danger1_t = x_nt_t
        # Use X_VS as danger2
        danger2_t = x_vs_t
        # Use X_BAT as danger3
        danger3_t = x_bat_t
        # Use X_ART as danger4
        danger4_t = x_art_t
        # Use X_RST as danger5
        danger5_t = x_rst_t
        # Use X_IC as danger6
        danger6_t = x_ic_t
        # Use X_ADC as danger7
        danger7_t = x_adc_t
        # Use X_USART as danger8
        danger8_t = x_usart_t
        # Calculate final danger indicators
        danger_t = min(1, (danger1_t + danger2_t + danger3_t + danger4_t + danger5_t + danger6_t + danger7_t + danger8_t))
        danger.append(danger_t)
        
        ### SAFE ###
        # Safe1 - T_air relative difference
        safe1_mu = 0
        for val in t_air_a:
            safe1_mu = safe1_mu + val
        safe1_mu = safe1_mu / len(t_air_a)
        safe1_dev = 0
        for val in t_air_a:
            safe1_dev = safe1_dev + ((val-safe1_mu)**2)
        safe1_dev = safe1_dev / len(t_air_a)
        safe1_dev = math.sqrt(safe1_dev)
        safe1_t = safe1_dev
        # Safe2 - T_soil relative difference
        safe2_mu = 0
        for val in t_soil_a:
            safe2_mu = safe2_mu + val
        safe2_mu = safe2_mu / len(t_soil_a)
        safe2_dev = 0
        for val in t_soil_a:
            safe2_dev = safe2_dev + ((val-safe2_mu)**2)
        safe2_dev = safe2_dev / len(t_soil_a)
        safe2_dev = math.sqrt(safe2_dev)
        safe2_t = safe2_dev
        # Safe3 - H_air relative difference
        safe3_mu = 0
        for val in h_air_a:
            safe3_mu = safe3_mu + val
        safe3_mu = safe3_mu / len(h_air_a)
        safe3_dev = 0
        for val in h_air_a:
            safe3_dev = safe3_dev + ((val-safe3_mu)**2)
        safe3_dev = safe3_dev / len(h_air_a)
        safe3_dev = math.sqrt(safe3_dev)
        safe3_t = safe3_dev
        # Safe4 - H_soil relative difference
        safe4_mu = 0
        for val in h_soil_a:
            safe4_mu = safe4_mu + val
        safe4_mu = safe4_mu / len(h_soil_a)
        safe4_dev = 0
        for val in h_soil_a:
            safe4_dev = safe4_dev + ((val-safe4_mu)**2)
        safe4_dev = safe4_dev / len(h_soil_a)
        safe4_dev = math.sqrt(safe4_dev)
        safe4_t = safe4_dev
        # Calculate final safe indicator
        safe_t  = math.exp(-max(safe1_t, safe2_t, safe3_t, safe4_t)*SAFE_SENS)
        safe.append(safe_t)


##########################################
##### Step 3 - dendritic cell update #####
##########################################
    
        context_t = danger_t - safe_t
        # Update previous DCs
        for dc in dcs:
            dc["context"] = dc["context"] + context_t
        # Create new DC
        dcs.append({
            "antigen"   : antigen_t,
            "context"   : context_t,
        })
        # If population is full, delete oldest DC
        if len(dcs)>DC_N:
            dcs.pop(0)
    

#######################################
##### Step 4 - context assignment #####
#######################################
    
        state = 0
        for dc in dcs:
            state = state + 1 if dc["context"]>=0 else state
        context.append(state/len(dcs))

    # Increment line counter
    line_count += 1

####################################
##### Step 1.2 - result output #####
####################################

# Close CSV input file
try:
    # Try to close the CSV file
    csv_f1.close()
except Exception as e:
    print("Couldn't close CSV input file ... aborting!")
    print(e)

### Save data to CSV file if required
if CSV_OUTPUT:
    # Iterate over all data
    for i in range(len(time)):
        try:
            # Write a row to the CSV file
            csv_o.writerow([snid[i], time[i], t_air[i], t_soil[i], h_air[i], h_soil[i], x_nt[i], x_vs[i], x_bat[i], x_art[i], x_rst[i], x_ic[i], x_adc[i], x_usart[i], antigen[i], danger[i], safe[i], context[i]])
        except Exception as e:
            print("Writing measurement data to the CSV file failed ... aborting!")
            print(e)
            exit(-1)
    # Close CSV output file
    try:
        # Try to close the CSV file
        csv_f2.close()
    except Exception as e:
        print("Couldn't close CSV output file ... aborting!")
        print(e)

### Plot the data via matplotlib
# get lowest (first) and highest (last) time
#x_first = hour_rounder(time[0])
#x_last  = hour_rounder(time[-1])

# prepare figure
fig = plt.figure(figsize=(15,8), dpi=300, tight_layout=True)
ax1 = fig.add_subplot(311)
ax1b = ax1.twinx()
ax2 = fig.add_subplot(312)
ax3 = fig.add_subplot(313)
ax3b = ax3.twinx()

## temperature/humidity plot
# grid
ax1.grid(which='major', color='#CCCCCC', linestyle=':')
# x-axis
ax1.xaxis.set_major_locator(AutoLocator())
ax1.xaxis.set_minor_locator(AutoMinorLocator(2))
ax1.set_xticklabels([])
ax1b.set_xticklabels([])
# y-axis
ax1.set_ylabel(r"temperature [$^{\circ}$C]")
#ax1.set_xlim(x_first,x_last)
ax1.set_ylim(0,40)
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)
ax1.yaxis.set_major_locator(MultipleLocator(10))
ax1.yaxis.set_minor_locator(AutoMinorLocator(2))
#ax1b.set_xlim(x_first,x_last)
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
lns1 = ax1.plot(time, t_air, '-',  label=r"$T_{air}$", color="darkgreen")
lns2 = ax1.plot(time, t_soil, '-',  label=r"$T_{soil}$", color="limegreen")
lns3 = ax1b.plot(time, h_air, '-',  label=r"$H_{air}$", color="darkblue")
lns4 = ax1b.plot(time, h_soil, '-',  label=r"$H_{soil}$", color="dodgerblue")
lns = lns1+lns2+lns3+lns4
labs = [l.get_label() for l in lns]
ax1b.legend(lns, labs, loc='upper right', facecolor='white', framealpha=1)

## indicator plot
# grid
ax2.grid(which='major', color='#CCCCCC', linestyle=':')
# x-axis
ax2.xaxis.set_major_locator(AutoLocator())
ax2.xaxis.set_minor_locator(AutoMinorLocator(2))
ax2.set_xticklabels([])
# y-axis
ax2.set_ylabel("fault indicators")
#ax2.set_xlim(x_first,x_last)
ax2.set_ylim(0,1.1)
ax2.yaxis.set_major_locator(MultipleLocator(0.25))
ax2.yaxis.set_minor_locator(AutoMinorLocator(1))
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)
# plot data
ax2.plot(time, x_nt, '-',  label=r"$\chi_{NT}$", color="midnightblue")
ax2.plot(time, x_vs, '-',  label=r"$\chi_{VS}$", color="darkgreen")
ax2.plot(time, x_bat, '-',  label=r"$\chi_{BAT}$", color="rosybrown")
ax2.plot(time, x_art, '-',  label=r"$\chi_{ART}$", color="orangered")
ax2.plot(time, x_rst, '-',  label=r"$\chi_{RST}$", color="fuchsia")
ax2.plot(time, x_ic, '-',  label=r"$\chi_{IC}$", color="lime")
ax2.plot(time, x_adc, '-',  label=r"$\chi_{ADC}$", color="aqua")
ax2.plot(time, x_usart, '-',  label=r"$\chi_{USART}$", color="gold")
ax2.legend(framealpha=1, ncol=8, loc='upper center')

## DCA plot
# grid
ax3.grid(which='major', color='#CCCCCC', linestyle=':')
# x-axis
ax3b.xaxis.set_major_locator(AutoLocator())
ax3b.xaxis.set_minor_locator(AutoMinorLocator(2))
ax3.set_xlabel('time [H:M]')
ax3.xaxis.set_major_formatter(xfmt)
ax3b.set_xlabel('time [H:M]')
ax3b.xaxis.set_major_formatter(xfmt)
# y-axis
ax3.set_ylabel("DCA indicators")
#ax3.set_xlim(x_first,x_last)
ax3.set_ylim(0,1.1)
ax3.yaxis.set_major_locator(MultipleLocator(0.25))
ax3.yaxis.set_minor_locator(AutoMinorLocator(1))
ax3.spines['top'].set_visible(False)
ax3.spines['right'].set_visible(False)
#ax3b.set_xlim(x_first,x_last)
ax3b.set_ylabel("anomaly context")
ax3b.set_ylim(0,1.1)
ax3b.spines['top'].set_visible(False)
ax3b.spines['left'].set_visible(False)
ax3b.xaxis.set_ticks_position('bottom')
ax3b.spines['bottom'].set_position(('data',0))
ax3b.yaxis.set_ticks_position('right')
ax3b.yaxis.set_major_locator(MultipleLocator(0.25))
ax3b.yaxis.set_minor_locator(AutoMinorLocator(1))
# plot data
lns1 = ax3.plot(time, danger, '-',  label="danger", color="red")
lns2 = ax3.plot(time, safe, '-',  label="safe", color="green")
lns3 = ax3b.plot(time, context, '-',  label="context", linewidth=1, color="blue")
lns = lns1+lns2+lns3
labs = [l.get_label() for l in lns]
ax3b.legend(lns, labs, loc='upper right', facecolor='white', framealpha=1)

### Finish figure
PLOT_FILE = Path(CSV_INPUT).stem + "-cdca.svg"
plt.savefig(PLOT_FILE)#, transparent=True)
plt.cla()
plt.clf()
plt.close()
