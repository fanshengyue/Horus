#!/usr/bin/python
#
# python Environment Sensor Observer for Linux
#
# target device : OMRON Environment Sensor (2JCIE-BL01) in Broadcaster mode
#
#
# Note: Proper operation of this sample application is not guaranteed.

import sys
import os
import argparse
import requests
import socket
import datetime
import threading
import struct
import json

import sensor_beacon as envsensor
import conf
import ble
from sqlalchemy import create_engine
from sqlalchemy import text

# constant
VER = 1.0

# ystem constant
GATEWAY = socket.gethostname()

# Global variables
flag_scanning_started = False
debug=False
sensor_list = []
flag_update_sensor_status = False
sock=None




def parse_events(sock):
    global sensor_list

    pkt = sock.recv(255)

    parsed_packet = ble.hci_le_parse_response_packet(pkt)

    if "bluetooth_le_subevent_name" in parsed_packet and \
            (parsed_packet["bluetooth_le_subevent_name"]
                == 'EVT_LE_ADVERTISING_REPORT'):

        if debug:
            for report in parsed_packet["advertising_reports"]:
                print "----------------------------------------------------"
                print "Found BLE device:", report['peer_bluetooth_address']
                print "Raw Advertising Packet:"
                print ble.packet_as_hex_string(pkt, flag_with_spacing=True,
                                               flag_force_capitalize=True)
                print ""
                for k, v in report.items():
                    if k == "payload_binary":
                        continue
                    print "\t%s: %s" % (k, v)
                print ""

        for report in parsed_packet["advertising_reports"]:
            if (ble.verify_beacon_packet(report)):
                sensor = envsensor.SensorBeacon(
                    report["peer_bluetooth_address_s"],
                    ble.classify_beacon_packet(report),
                    GATEWAY,
                    report["payload_binary"])

                index = find_sensor_in_list(sensor, sensor_list)

                if debug:
                    print ("\t--- sensor data ---")
                    sensor.debug_print()
                    print ""

                lock = threading.Lock()
                lock.acquire()
                with open('/home/nvidia/Horus/config.cnf') as f:
                    cnf = json.load(f)
                conn = create_engine(cnf['db'])

                if (index != -1):  # BT Address found in sensor_list
                    if sensor.check_diff_seq_num(sensor_list[index]):
                        conn.execute(sensor.sqlInsert())
                    sensor.update(sensor_list[index])
                else:  # new SensorBeacon
                    sensor_list.append(sensor)
                    conn.execute(sensor.sqlInsert())
                lock.release()
            else:
                pass
    else:
        pass
    return



# check timeout sensor and update flag
def eval_sensor_state():
    global flag_update_sensor_status
    global sensor_list
    nowtick = datetime.datetime.now()
    for sensor in sensor_list:
        if (sensor.flag_active):
            pastSec = (nowtick - sensor.tick_last_update).total_seconds()
            if (pastSec > conf.INACTIVE_TIMEOUT_SECONDS):
                if debug:
                    print "timeout sensor : " + sensor.bt_address
                sensor.flag_active = False
    flag_update_sensor_status = True
    with open('/home/nvidia/Horus/config.cnf') as f:
        cnf = json.load(f)
    timer = threading.Timer(int(cnf['check_sensor_state_interval_seconds']),
                            eval_sensor_state)
    timer.setDaemon(True)
    timer.start()


def print_sensor_state():
    print "----------------------------------------------------"
    with open('/home/nvidia/Horus/config.cnf') as f:
        cnf = json.load(f)
    print ("sensor status : %s (Intvl. %ssec)" % (datetime.datetime.today(),int(cnf['check_sensor_state_interval_seconds'])))
    for sensor in sensor_list:
        print " " + sensor.bt_address, ": %s :" % sensor.sensor_type, \
            ("ACTIVE" if sensor.flag_active else "DEAD"), \
            "(%s)" % sensor.tick_last_update
    print ""



def find_sensor_in_list(sensor, List):
    index = -1
    count = 0
    for i in List:
        if sensor.bt_address == i.bt_address:
            index = count
            break
        else:
            count += 1
    return index


# command line argument
def arg_parse():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--debug', help='debug mode',
                        action='store_true')
    parser.add_argument('--version', action='version',
                        version='%(prog)s ' + str(VER))
    args = parser.parse_args()
    return args


# main function
def evsensor():
    # print('called')
    sys.path.append("..")
    import util
    try:
        # process command line arguments
        debug = False
        args = arg_parse()
        if args.debug:
            debug = False

        # reset bluetooth functionality
        try:
            if debug:
                print "-- reseting bluetooth device"
            ble.reset_hci()
            if debug:
                print "-- reseting bluetooth device : success"
        except Exception as e:
            util.Logprint(4, "error enabling bluetooth device")
            # print "error enabling bluetooth device"
            # print str(e)
            sys.exit(1)

        # initialize bluetooth socket
        try:
            if debug:
                print "-- open bluetooth device"
            sock = ble.bluez.hci_open_dev(conf.BT_DEV_ID)
            if debug:
                print "-- ble thread started"
        except Exception as e:
            util.Logprint(4, "error accessing bluetooth device")
            # print "error accessing bluetooth device: ", str(conf.BT_DEV_ID)
            # print str(e)
            sys.exit(1)

        # set ble scan parameters
        try:
            if debug:
                print "-- set ble scan parameters"
            ble.hci_le_set_scan_parameters(sock)
            if debug:
                print "-- set ble scan parameters : success"
        except Exception as e:
            util.Logprint(4, "failed to set scan parameter!!")
            # print "failed to set scan parameter!!"
            # print str(e)
            sys.exit(1)

        # start ble scan
        try:
            if debug:
                print "-- enable ble scan"
            ble.hci_le_enable_scan(sock)
            if debug:
                print "-- ble scan started"
        except Exception as e:
            util.Logprint(4, "failed to activate scan!!")
            # print "failed to activate scan!!"
            # print str(e)
            sys.exit(1)

        global flag_scanning_started
        flag_scanning_started = True

        util.Logprint(1,"envsensor_observer : complete initialization")
        # print ("envsensor_observer : complete initialization")
        # print ""

        # preserve old filter setting
        old_filter = sock.getsockopt(ble.bluez.SOL_HCI,
                                     ble.bluez.HCI_FILTER, 14)
        # perform a device inquiry on bluetooth device #0
        # The inquiry should last 8 * 1.28 = 10.24 seconds
        # before the inquiry is performed, bluez should flush its cache of
        # previously discovered devices
        flt = ble.bluez.hci_filter_new()
        ble.bluez.hci_filter_all_events(flt)
        ble.bluez.hci_filter_set_ptype(flt, ble.bluez.HCI_EVENT_PKT)
        sock.setsockopt(ble.bluez.SOL_HCI, ble.bluez.HCI_FILTER, flt)

        # activate timer for sensor status evaluation
        with open('/home/nvidia/Horus/config.cnf') as f:
            cnf = json.load(f)
        timer = threading.Timer(int(cnf['check_sensor_state_interval_seconds']),
                                eval_sensor_state)

        timer.setDaemon(True)
        timer.start()

        global flag_update_sensor_status
        while True:
            # parse ble event
            parse_events(sock)
            if flag_update_sensor_status:
                # print_sensor_state()
                flag_update_sensor_status = False

    except Exception as e:
        # print "Exception: " + str(e)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        if flag_scanning_started:
            # restore old filter setting
            sock.setsockopt(ble.bluez.SOL_HCI, ble.bluez.HCI_FILTER,
                            old_filter)
            ble.hci_le_disable_scan(sock)
        # print "Exit"
