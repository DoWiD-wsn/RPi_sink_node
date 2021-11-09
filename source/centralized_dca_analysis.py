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
# @version  0.1.3
# @date     2021/11/08
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
# Hash functionality (for antigens)
import hashlib
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

# use certain period (otherwise all data will be used)
USE_PERIOD      = 1
# Period to analyze
p_start         = "2021-11-07 12:00:00"
p_end           = "2021-11-09 12:00:00"

# Sensor node ID (use single nodes for now)
nodes           = [
                    "41B9F864", # SNx
                    "41B9F805","41B9FFC2","41B9FFD8","41B9FFDD","41B9FD22","41BA26F1", # SN1-SN6
                    "41CC57CC","41CC3F83","41CC3E8F","41CC5591" # SN7-SN10
                  ]

# CSV output (0...disable/1...enable)
CSV_OUTPUT      = 1

# DB CONNECTION
DB_CON_HOST     = "10.128.211.4"
DB_CON_USER     = "mywsn"
DB_CON_PASS     = "$MyWSNdemo$"
DB_CON_BASE     = "wsn_testbed"

# Date/time format
fmt             = '%Y-%m-%d %H:%M:%S'
xfmt            = md.DateFormatter('%H:%M\n%m/%d')


##### METHODS #####################
# See https://www.codegrepper.com/code-examples/python/python+datetime+round+to+nearest+hour
def hour_rounder(t):
    # Rounds to nearest hour by adding a timedelta hour if minute >= 30
    return (t.replace(second=0, microsecond=0, minute=0, hour=t.hour)
               +timedelta(hours=t.minute//30))

def fixed16_to_float(value, f_bits):
    # Convert fixed16 to float
    tmp = (float(value & 0x7FFF) / float(1 << f_bits))
    # Check sign of input
    if(value & 0x8000):
        tmp *= -1
    # Return the float value
    return tmp

def float_to_fixed16(value, f_bits):
    tmp = 0x0000
    # Check sign of input
    if(value<0):
        value *= -1
        tmp |= 0x8000
    # Convert float to fixed16
    tmp = tmp | (int(value * (1 << f_bits)) & 0x7FFF);
    # Return the fixed16 value
    return tmp

def fixed16_to_float_10to6(value):
    return fixed16_to_float(value,6)

def float_to_fixed16_10to6(value):
    return float_to_fixed16(value,6)


###################################
##### Step 0 - initialization #####
###################################

if USE_PERIOD:
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

for SNID in nodes:
    # Prepare query string
    if USE_PERIOD:
        query = "SELECT * FROM `sensordata` WHERE `snid` LIKE '" + SNID + "' AND (`dbtime` BETWEEN '" + start_utc_str + "' AND '" + end_utc_str + "') ORDER BY `id` ASC"
    else:
        query = "SELECT * FROM `sensordata` WHERE `snid` LIKE '" + SNID + "' ORDER BY `id` ASC"
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
        print("There was no data for \"%s\" ... skipping" % SNID)
        continue

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
    for row in entries:
        ### GENERAL ###
        # Get snid
        snid_t = str(row[1])
        snid.append(snid_t)
        # Get sntime
        sntime_t = int(row[2])
        sntime.append(sntime_t)
        # Get datetime from row
        dtime_t = datetime.strptime(str(row[3]), fmt) + timedelta(hours = 2)
        # Add datetime to time array
        time.append(dtime_t)
        # Convert datetime to UNIX timestamp
        tstmp.append(int(datetime.timestamp(dtime_t)))
        
        ### USE CASE DATA ###
        # Get sensor readings
        t_air_t = round(float(row[4]),2)
        t_air.append(t_air_t)
        t_soil_t = round(float(row[5]),2)
        t_soil.append(t_soil_t)
        h_air_t = round(float(row[6]),2)
        h_air.append(h_air_t)
        h_soil_t = round(float(row[7]),2)
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
        x_nt_t = round(float(row[8]),2)
        x_nt.append(x_nt_t)
        x_vs_t = round(float(row[9]),2)
        x_vs.append(x_vs_t)
        x_bat_t = round(float(row[10]),2)
        x_bat.append(x_bat_t)
        x_art_t = round(float(row[11]),2)
        x_art.append(x_art_t)
        x_rst_t = round(float(row[12]),2)
        x_rst.append(x_rst_t)
        x_ic_t = round(float(row[13]),2)
        x_ic.append(x_ic_t)
        x_adc_t = round(float(row[14]),2)
        x_adc.append(x_adc_t)
        x_usart_t = round(float(row[15]),2)
        x_usart.append(x_usart_t)


    ##################################
    ##### Step 2 - signal update #####
    ##################################
        
        ### ANTIGEN ###
        # use SNID as antigen
        antigen_t = SNID
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
        danger_t = min(1, ((1+danger1_t) * (1+danger2_t) * (1+danger3_t) * (1+danger4_t) * (1+danger5_t) * (1+danger6_t) * (1+danger7_t) * (1+danger8_t)) - 1)
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

    ####################################
    ##### Step 1.2 - result output #####
    ####################################

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
    ax2.set_xlim(x_first,x_last)
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
    ax3.set_xlim(x_first,x_last)
    ax3.set_ylim(0,1.1)
    ax3.yaxis.set_major_locator(MultipleLocator(0.25))
    ax3.yaxis.set_minor_locator(AutoMinorLocator(1))
    ax3.spines['top'].set_visible(False)
    ax3.spines['right'].set_visible(False)
    ax3b.set_xlim(x_first,x_last)
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
    PLOT_FILE = "centralized_dca-%s-output.svg" % SNID
    plt.savefig(PLOT_FILE)#, transparent=True)
    plt.cla()
    plt.clf()
    plt.close()


### Close database connection
if db_con.is_connected():
    db_cur.close()
    db_con.close()
