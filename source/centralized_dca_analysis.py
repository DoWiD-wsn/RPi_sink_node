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
# Hash functionality (for antigens)
import hashlib
# for plotting
import matplotlib.pyplot as plt
plt.rcParams.update({'font.size': 12})
from matplotlib import rc
rc('mathtext', default='regular')
from matplotlib.ticker import (AutoMinorLocator, MultipleLocator)
import matplotlib.dates as md


##### GLOBAL VARIABLES #####
# dendritic cell lifetime/population
DC_N            = 5
# use the dDCA (otherwise DCA will be used)
USE_DDCA        = 0

# use certain period (otherwise all data will be used)
USE_PERIOD      = 0
# Period to analyze
p_start         = "2021-10-20 12:00:00"
p_end           = "2021-10-21 12:00:00"

# Sensor node ID (use single nodes for now)
nodes           = [
                    "41B9F864", # SNx
                    "41B9F805","41B9FFC2","41B9FFD8","41B9FFDD","41B9FD22","41BA26F1", # SN1-SN6
                    "41CC57CC","41CC3F83","41CC3E8F","41CC5591" # SN7-SN10
                  ]

# CSV output (0...disable/1...enable)
CSV_OUTPUT      = 1

# PAMP indicator weights
pamp1_w         = 1
pamp2_w         = 1
# Danger indicator weights
danger1_w       = 1
danger2_w       = 1
danger3_w       = 1
danger4_w       = 1
danger5_w       = 1
danger6_w       = 1
danger7_w       = 1
# Safe indicator weights
safe1_w         = 1
safe2_w         = 1
safe3_w         = 1
safe4_w         = 1
# DCA weights
pamp_w_csm      = 1
danger_w_csm    = 1
safe_w_csm      = 2
pamp_w_semi     = 0
danger_w_semi   = 0
safe_w_semi     = 3
pamp_w_mat      = 2
danger_w_mat    = 1
safe_w_mat      = -3

# DB CONNECTION
DB_CON_HOST     = "192.168.13.98"
DB_CON_USER     = "mywsn"
DB_CON_PASS     = "$MyWSNdemo$"
DB_CON_BASE     = "wsn_testbed"

# Date/time format
fmt             = '%Y-%m-%d %H:%M:%S'
xfmt            = md.DateFormatter('%H:%M')


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

def get_delta(v1,v2):
    # Check if both are equal
    if v1 == v2:
        return 0.0
    # Check if at least one is bigger than zero
    if (v1 != 0.0) or (v2 != 0.0):
        base = abs(v1) if (v1 != 0.0) else abs(v2)
    # Calculate difference
    delta = abs((t_air[i]) - (t_air[i-1]))
    # Scale difference
    #delta = delta / base
    # Return delta
    return delta


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
            csv_o.writerow(["snid [lower 32-bit of MAC]", "time [UNIX]", "T_air [°C]", "T_soil [°C]", "H_air [%RH]", "H_soil [%RH]", "x_nt",  "x_vs",  "x_bat",  "x_art",  "x_rst",  "x_ic",  "x_adc",  "x_usart", "antigen",  "PAMP",  "danger",  "safe", "context [0..1]"])
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
    pamp        = []
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
    i = 0
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
        
        ## or
        
        # use 32-bit hash of sensor values as antigen
        # antigen_t = hashlib.sha1(("%04X%04X%04X%04X" % (float_to_fixed16_10to6(t_air_t),float_to_fixed16_10to6(t_soil_t),float_to_fixed16_10to6(h_air_t),float_to_fixed16_10to6(h_soil_t))).encode()).hexdigest()[:8].upper()
        # comment: may not be the best way since an affinity measure is hard to implement for the hash
        
        # Store antigen
        antigen.append(antigen_t)
        
        ### PAMP ###
        # Use X_RST as PAMP1
        pamp1_t = x_rst_t * pamp1_w
        # Use difference in the consecutive message counter as PAMP2
        if(i>0):
            # Check delta between message numbers
            if (sntime[i]-sntime[i-1]) != 1:
                pamp2_t = 1.0 * pamp2_w
            else:
                pamp2_t = 0.0
        else:
            # PAMP2 is zero
            pamp2_t = 0.0
        # Get sum of weights
        pamp_w_sum = abs(pamp1_w) + abs(pamp2_w)
        # Calcualte sum of pamp indicators
        pamp_t = (pamp1_t + pamp2_t)
        # Add final PAMP to array
        pamp.append(pamp_t)
        
        ### DANGER ###
        # Use X_NT as danger1
        danger1_t = x_nt_t * danger1_w
        # Use X_VS as danger2
        danger2_t = x_vs_t * danger2_w
        # Use X_BAT as danger3
        danger3_t = x_bat_t * danger3_w
        # Use X_ART as danger4
        danger4_t = x_art_t * danger4_w
        # Use X_IC as danger5
        danger5_t = x_ic_t * danger5_w
        # Use X_ADC as danger6
        danger6_t = x_adc_t * danger6_w
        # Use X_USART as danger7
        danger7_t = x_usart_t * danger7_w
        # Calculate sum of weights
        danger_w_sum = abs(danger1_w) + abs(danger2_w) + abs(danger3_w) + abs(danger4_w) + abs(danger5_w) + abs(danger6_w) + abs(danger7_w)
        # Calculate sum of danger indicators
        danger_t = (danger1_t + danger2_t + danger3_t + danger4_t + danger5_t + danger6_t + danger7_t)
        # Add to array
        danger.append(danger_t)
        
        ### SAFE ###
        safe_t = 0.0
        if(i>0):
            # Use Delta(t_air(t),t_air(t-1)) as safe signal1
            safe1_t = get_delta(t_air[i],t_air[i-1]) * safe1_w
            # Use Delta(t_soil(t),t_soil(t-1)) as safe signal2
            safe2_t = get_delta(t_soil[i],t_soil[i-1]) * safe2_w
            # Use Delta(h_air(t),h_air(t-1)) as safe signal3
            safe3_t = get_delta(h_air[i],h_air[i-1]) * safe3_w
            # Use Delta(h_soil(t),h_soil(t-1)) as safe signal4
            safe4_t = get_delta(h_soil[i],h_soil[i-1]) * safe4_w
            # Calculate sum of weights
            safe_w_sum = abs(safe1_w) + abs(safe2_w) + abs(safe3_w) + abs(safe4_w)
            # Calculate sum of safe indicators
            safe_t = (safe1_t + safe2_t + safe3_t + safe4_t) / safe_w_sum
            # Safe indicator is the higher with lower deltas
            safe_t = 1.0 - safe_t
            # Add to array
            safe.append(safe_t)
        else:
            # Add 0 to array
            safe.append(0.0)


    ##########################################
    ##### Step 3 - dendritic cell update #####
    ##########################################
        
        ##### dDCA #####
        if USE_DDCA:
            ### We use the PAMP as part of the danger signal ###
            # CSM
            csm = safe_t + (danger_t + 2*pamp_t)
            # K
            k = (danger_t + 2*pamp_t) - 2*safe_t
            # Update previous DCs
            for dc in dcs:
                dc["csm"] = dc["csm"] + csm
                dc["k"] = dc["k"] + k
            # Create new DC
            dcs.append({
                "antigen": antigen_t,
                "csm" : csm,
                "k": k,
            })
        ##### DCA #####
        else:
            # CSM
            csm_w_sum = abs(pamp_w_csm) + abs(safe_w_csm) + abs(danger_w_csm)
            csm = ((pamp_t*pamp_w_csm) + (safe_t*safe_w_csm) + (danger_t*danger_w_csm)) / csm_w_sum
            # SEMI-MATURE
            semi_w_sum = abs(pamp_w_semi) + abs(safe_w_semi) + abs(danger_w_semi)
            semi = ((pamp_t*pamp_w_semi) + (safe_t*safe_w_semi) + (danger_t*danger_w_semi)) / semi_w_sum
            # MATURE
            mat_w_sum = abs(pamp_w_mat) + abs(safe_w_mat) + abs(danger_w_mat)
            mat = ((pamp_t*pamp_w_mat) + (safe_t*safe_w_mat) + (danger_t*danger_w_mat)) / mat_w_sum
            # Update previous DCs
            for dc in dcs:
                dc["csm"] = dc["csm"] + csm
                dc["semi"] = dc["semi"] + semi
                dc["mat"] = dc["mat"] + mat
            # Create new DC
            dcs.append({
                "antigen": antigen_t,
                "csm" : csm,
                "semi": semi,
                "mat" : mat
            })
        

    #######################################
    ##### Step 4 - context assignment #####
    #######################################
        
        # Check if there is a DC at the end of its life
        if len(dcs)>4:
            # Get ready DC
            dc = dcs.pop(0)
            ##### dDCA #####
            if USE_DDCA:
                # Asses the DC's context
                if (dc["k"]>0):
                    context.append(1.0)
                else:
                    context.append(0.0)
            ##### DCA #####
            else:
                # Asses the DC's context
                if (dc["mat"]>dc["semi"]):
                    context.append(1.0)
                else:
                    context.append(0.0)
        else:
            context.append(0.0)
        
        # Increment iteration counter
        i = i + 1

    ####################################
    ##### Step 1.2 - result output #####
    ####################################

    ### Save data to CSV file if required
    if CSV_OUTPUT:
        # Iterate over all data
        for i in range(len(time)):
            try:
                # Write a row to the CSV file
                csv_o.writerow([snid[i], time[i], t_air[i], t_soil[i], h_air[i], h_soil[i], x_nt[i], x_vs[i], x_bat[i], x_art[i], x_rst[i], x_ic[i], x_adc[i], x_usart[i], antigen[i], pamp[i], danger[i], safe[i], context[i]])
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
    fig = plt.figure(figsize=(12,8), dpi=150, tight_layout=True)
    ax1 = fig.add_subplot(311)
    ax1b = ax1.twinx()
    ax2 = fig.add_subplot(312)
    ax3 = fig.add_subplot(313)
    ax3b = ax3.twinx()

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
    lns1 = ax1.plot(time, t_air, '-',  label=r"$T_{air}$", linewidth=1, color="darkgreen")
    lns2 = ax1.plot(time, t_soil, '-',  label=r"$T_{soil}$", linewidth=1, color="limegreen")
    lns3 = ax1b.plot(time, h_air, '-',  label=r"$H_{air}$", linewidth=1, color="darkblue")
    lns4 = ax1b.plot(time, h_soil, '-',  label=r"$H_{soil}$", linewidth=1, color="dodgerblue")
    lns = lns1+lns2+lns3+lns4
    labs = [l.get_label() for l in lns]
    ax1b.legend(lns, labs, loc='upper right', facecolor='white', framealpha=1)

    ## indicator plot
    # grid
    ax2.grid(which='major', color='#CCCCCC', linestyle=':')
    # x-axis
    ax2.xaxis.set_major_locator(md.HourLocator(interval = 12))
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
    ax2.plot(time, x_nt, '-',  label=r"$\chi_{NT}$", linewidth=1, color="red")
    ax2.plot(time, x_vs, '-',  label=r"$\chi_{VS}$", linewidth=1, color="darkred")
    ax2.plot(time, x_bat, '-',  label=r"$\chi_{BAT}$", linewidth=1, color="slateblue")
    ax2.plot(time, x_art, '-',  label=r"$\chi_{ART}$", linewidth=1, color="magenta")
    ax2.plot(time, x_rst, '-',  label=r"$\chi_{RST}$", linewidth=1, color="chocolate")
    ax2.plot(time, x_ic, '-',  label=r"$\chi_{IC}$", linewidth=1, color="darkviolet")
    ax2.plot(time, x_adc, '-',  label=r"$\chi_{ADC}$", linewidth=1, color="darkorange")
    ax2.plot(time, x_usart, '-',  label=r"$\chi_{USART}$", linewidth=1, color="darkviolet")
    ax2.legend(framealpha=1, ncol=8, loc='upper center')

    ## DCA plot
    # grid
    ax3.grid(which='major', color='#CCCCCC', linestyle=':')
    # x-axis
    ax3b.xaxis.set_major_locator(md.HourLocator(interval = 12))
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
    lns1 = ax3.plot(time, pamp, '-',  label="PAMP", linewidth=1, color="red")
    lns2 = ax3.plot(time, danger, '-',  label="danger", linewidth=1, color="orange")
    lns3 = ax3.plot(time, safe, '-',  label="safe", linewidth=1, color="green")
    lns4 = ax3b.plot(time, context, '-',  label="context", linewidth=1, color="blue")
    lns = lns1+lns2+lns3+lns4
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
