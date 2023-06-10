#!/usr/bin/env python3
#Purpose: read some ds18b20 probes and upload to misc places
# 1 - read the DS18B20 temp probes
# 2 - upload them to mqtt
# 3 - upload info to influx
# 4 - stor the data in a db
# 5 - check if temp diff indicates furnace heating/cooling
#

################################################################
# Stuff below shouldn't have to change
# all config parameters are in the config file


import os
import glob
import time
import sys
from time import gmtime, strftime
from datetime import datetime
import configparser
import getopt
import json
import signal

#Try to import some modules
#if they don't exist just ignore it, if they are requred it will fail later
#
try:
    # sudo apt install python3-mysqldb
    import MySQLdb
except:
    pass

try:
    # sudo apt install python3-paho-mqtt
    import paho.mqtt.client as mqtt
except:
    pass

try:
    # https://github.com/influxdata/influxdb-client-python
    from influxdb_client import InfluxDBClient, Point, WriteOptions
except:
    pass

#Should already be done
#os.system('sudo modprobe w1-gpio')
#os.system('sudo modprobe w1-therm')

Version=0.6

#Location of all ds18b20 probes
base_dir = '/sys/bus/w1/devices/'
devicepath=glob.glob(base_dir + '28*')
if len(devicepath)>0:
    device_folder = devicepath[0]
else:
    device_folder=base_dir+"28-00000000"

device_file = device_folder + '/w1_slave'

sensor_value=dict()


#  -utempdata -pdatatemp TempData 


####
#influx
def send_to_influx(unit,desc,temp_c):
        #'RF,host=rpi5 unit="37D1E63F",msgCnt=28761,vcc_mV=5120,batt_mV=5120,stat=0,temp_c=19.70,humid_pct=1.40'
        # iot_sensor,hostname={},type=temperature value={}'.format(socket.gethostname(), temperature)
    try:
        p = Point("DS")\
            .tag("host",os.uname()[1])\
            .tag("unit",unit)\
            .tag("desc",desc)\
            .field("temp_c",float(temp_c))
    except:
        print ("creating a datapoint failed: {} - {}".format(sys.exc_info()[0],sys.exc_info()[1]))

        
    try:
        write_api.write(bucket=influx_info["INFLUX_BUCKET"], record=p)
    except:
        print ("write to influx failed: {} - {}".format(sys.exc_info()[0],sys.exc_info()[1]))
        exit(91)

    #flush the data
    write_api.close()

#mqtt
def on_connect(mqtt_client, userdata, flags, rc):
    if rc == 0:
        print("#Connected success")
    else:
        print(f"Connected fail with code {rc}", file=sys.stderr)
        if ( rc in mqtt_info["MQTT_RETURNCODES"]):
            print(f"  {mqtt_info['MQTT_RETURNCODES'][rc]}", file=sys.stderr)
        else:
            print("unknown error code", file=sys.stderr)

#mqtt
def send_to_mqtt(unit,desc,temp_c):
    payload={
        "unit":unit,
        "desc":desc,
        "temp_c":temp_c
        }
    if (desc != "unknown"):
        topic=mqtt_info["MQTT_TOPIC"]+"/"+desc
    else:
        topic=mqtt_info["MQTT_TOPIC"]+"/"+str(unit)

    result = mqtt_client.publish(topic, payload=json.dumps(payload), qos=0, retain=False)
    # result: [0, 1]
    status = result[0]
    if status == 0:
        # if DEBUG:
        #     print(f"# Sent `{json.dumps(payload)}` to topic `{topic}`", file=sys.stderr)
        pass
    else:
        print(f"# Failed to send message to topic {topic}, status={status}", file=sys.stderr)


################
#Single function to read raw temp of one sensor
#error handling that returns crc=NO if read error of file
def read_temp_raw(sensor):
    f = open(sensor, 'r')
    lines = f.readlines()
    f.close()
    try:
        crcok=lines[0].strip()[-3:]
        temp_string = lines[1].split('=')[1].strip()
    except:
        #print(lines, file=sys.stderr)
        # just some dummy values so it doesn't crash and tries again
        lines=['47 01 4b 46 7f ff 09 10 93 : crc=xx NO\n', '47 01 4b 46 7f ff 09 10 93 t=20437\n']
    return lines

################
#Read the temp sensor
def read_temp(sensor):
    lines = read_temp_raw(sensor)
    while lines[0].strip()[-3:] != 'YES':
        time.sleep(0.2)
        lines = read_temp_raw(sensor)

    equals_pos = lines[1].find('t=')
    if equals_pos != -1:
        unitId=sensor.split("/")[5].split("-")[1]
        temp_string = lines[1][equals_pos+2:]
        temp_c = float(temp_string) / 1000.0
        if unitId in allocation:
            desc=allocation[unitId]
        else:
            #print(lines)
            desc="unknown"
        #send_to_mqtt(unitId,desc,msgCnt,vcc_mV,batt_mV,stat,temp_c,humid_pct)
        return unitId,temp_c,desc

################
#just close files and so on

def end_program():
    print(f"{datetime()}; ending program", file=sys.stderr)
    try:
        dbconn.close()
    except:
        pass

    try:
        write_api.close()
    except:
        pass

################################################################
# initialization

def signal_term_handler(signal, frame):
#    print(f"got SIGTERM - {signal} - {frame}")
    print("got SIGTERM", file=sys.stderr)
    end_program()
    sys.exit(0)

signal.signal(signal.SIGTERM, signal_term_handler)

################
#
def help():
    print (f"{sys.argv[0]} version {Version}")
    print("usage:")
    print (f"  {sys.argv[0]} [-d|--debug] [-v|--verbose] [-c|--config <configfile>] [-o|--outfile] <outputfile> [-s|--statefile] <statefile>")
    print (" -c <configfile> if defined, a .ini file with the config for the rest, default config.ini. If missing a default file will be created")
    print ("  <outfile>    if defined, a csv file that values are appended to. If the file doesn't exist it's created")
    print ("  <statefile>  if defined, a csv file with a indicator whenever the heat/cool is on")

def parse_opt(argv):
    global configfile
    global statefile
    global outputfile
    global DEBUG
    global VERBOSE
    configfile="log_temp.ini"
    #configfile='config.ini'
    statefile=''
    outputfile=''
    DEBUG=False
    VERBOSE=False

    try:
        opts, args = getopt.getopt(argv[1:],"h?dvc:o:s:",["help","debug","verbose","configfile=","outfile=","statefile="])
    except getopt.GetoptError as e:
        print("parsing error")
        print("  ",e)
        print()
        help()
        sys.exit(28)

    for opt, arg in opts:
        if opt in ('-h',"-?","--help"):
            help()
            sys.exit()
        elif opt in ("-d","--debug"):
            DEBUG=True
        elif opt in ("-v","--verbose"):
            VERBOSE=True
        elif opt in ("-c", "--configfile"):
            configfile = arg
        elif opt in ("-s", "--statefile"):
            statefile = arg
        elif opt in ("-o", "--outfile"):
            outputfile = arg
    if DEBUG:
        print (f"config file: {configfile}")
        print (f"Output file: {outputfile}")
        print (f"State file:  {statefile}")

def config_parse():
    global config
    global allocation
    global max_log_time,max_list_length,min_time_between_reads,min_temp_diff
    global db_enabled,db,db_info,dbconn
    global mqtt_enabled,mqtt_info,mqtt_client
    global influx_enabled,influx_info,write_api

    db_enabled=False
    mqtt_enabled=False
    influx_enabled=False

    config = configparser.ConfigParser(interpolation=configparser.ExtendedInterpolation())

    if os.path.isfile(configfile):
        config.read(configfile)
    else:
        #Fill it with some default info and save it
        config['config']={
            "max_log_time":60,
            "max_list_length":10,
            "min_time_between_reads":1,
            "min_temp_diff":0.5
        }

        config['sensors'] = {}
        config['sensors']['allocation'] ="""{
                "000000000123" : "before_furnace",
                "000000000456" : "after_furnace"
            }"""

        config['mqtt']={}
        config['mqtt']["enabled"]="false"
        config['mqtt']["mqtt_info"] = """{
                "MQTT_SERVER":"mqtt.example.com",
                "MQTT_PORT":1883,
                "MQTT_TOPIC":"temperature",
                "MQTT_USER":"temperature",
                "MQTT_PASSWORD":"mysecretpassword",
                "MQTT_SUBTOPICS":["unit","temp_c","desc"],
                "MQTT_RETURNCODES":{
                    "0" : "connection succeeded",
                    "1" : "connection failed - incorrect protocol version",
                    "2" : "connection failed - invalid client identifier",
                    "3" : "connection failed - the broker is not available",
                    "4" : "connection failed - wrong username or password",
                    "5" : "connection failed - unauthorized"
                 }
            }
        """

        config['db']={}
        config['db']["enabled"]="false"
        config['db']["db_info"]="""{
                "host":"localhost",
                "port":3306,
                "database":"TempData",
                "user":"tempdata",
                "password":"mysecretpassword"
            }
        """

        config['influx']={}
        config['influx']["enabled"]="no"
        config['influx']["influx_info"]="""{
               "INFLUX_URL":"http://influxdb.example.com:8086",
               "INFLUX_TOKEN":"alongstringrepresentingtheinfluxapitoken",
               "INFLUX_ORG":"example",
               "INFLUX_BUCKET":"Temperatures"
           }
        """

        with open(configfile, 'w') as f:
            config.write(f)

    if DEBUG:
        with open('debug.ini', 'w') as f:
            config.write(f)


    # debug stuff, show the config
    if DEBUG:
        print("DEBUG: config info;")
        for sec in config.sections():
            print(f"[{sec}]")
            for key in config[sec]:
                val=config[sec][key]
                print(f"  {key}={val}")
                # if "parts" in key:
                #     print(f">>>{val}\n   type={type(val)}")
                #     y=(json.loads(val))
                #     print(f"*** list {y}\n   type={type(y)}\n   lenght={len(y)}")

    #convert config strings to "real" values - as needed
    max_log_time=60
    max_list_length=10
    min_time_between_reads=0
    min_temp_diff=0.5
    if "max_log_time" in config['config']:
        try:
            max_log_time=int(config['config']['max_log_time'])
        except:
            pass

    if "max_list_length" in config['config']:
        try:
            max_list_length=int(config['config']['max_list_length'])
        except:
            pass

    if "min_time_between_reads" in config['config']:
        try:
            min_time_between_reads=int(config['config']['min_time_between_reads'])
        except:
            pass

    if "min_temp_diff" in config['config']:
        try:
            min_temp_diff=int(config['config']['min_temp_diff'])
        except:
            pass

    try:
        allocation=json.loads(config['sensors']['allocation'])
    except:
        allocation={}

    YES=("y","yes","true")
    #mysql db
    if "enabled" in config['db'] and config['db']['enabled'].lower().strip('"').strip() in YES:
        db_enabled=True
        if VERBOSE:
            print("connecting to db")
        try:
            db_info=json.loads(config['db']['db_info'])
            try:
                dbconn = MySQLdb.connect(
                    user=db_info["user"],
                    password=db_info["password"],
                    host=db_info["host"],
                    port=db_info["port"],
                    database=db_info["database"],
                )
            except MySQLdb.Error as e:
                print(f"Error connecting to MySQLdb Platform: {e}", file=sys.stderr)
                exit(30)
        except:
            #print ("db connection failed failed: {} - {}".format(sys.exc_info()[0],sys.exc_info()[1]), file=sys.stderr)
            print ("db connection failed failed: {} - {}".format(sys.exc_info()), file=sys.stderr)
            exit(31)

    #mqtt
    if "enabled" in config['mqtt'] and config['mqtt']['enabled'].lower().strip('"').strip() in YES:
        mqtt_enabled=True
        if VERBOSE:
            print("connecting to mqtt")
        try:
            mqtt_info=json.loads(config['mqtt']['mqtt_info'])
            mqtt_client = mqtt.Client()
            mqtt_client.username_pw_set(mqtt_info["MQTT_USER"],mqtt_info["MQTT_PASSWORD"])
            mqtt_client.on_connect = on_connect
            mqtt_client.connect(mqtt_info["MQTT_SERVER"], mqtt_info["MQTT_PORT"], 60)
        except:
            print ("mqtt connection failed failed: {} - {}".format(sys.exc_info()[0],sys.exc_info()[1]), file=sys.stderr)
            exit(32)

    # influx
    if "enabled" in config['influx'] and config['influx']['enabled'].lower().strip('"').strip() in YES:
        influx_enabled=True
        if VERBOSE:
            print("connecting to influx")
        try:
            influx_info=json.loads(config['influx']['influx_info'])
            influx_client = InfluxDBClient(url=influx_info["INFLUX_URL"], token=influx_info["INFLUX_TOKEN"],org=influx_info["INFLUX_ORG"])
            #define write_api for use later (maybe move this values to the config file?)
            write_api = influx_client.write_api(write_options=WriteOptions(write_type=3,  
                                                                batch_size=500,
                                                                flush_interval=10_000,
                                                                jitter_interval=2_000,
                                                                retry_interval=5_000,
                                                                max_retries=5,
                                                                max_retry_delay=30_000,
                                                                exponential_base=2))
        except:
            print ("influx connection failed failed: {} - {}".format(sys.exc_info()[0],sys.exc_info()[1]), file=sys.stderr)
            exit(33)

    if not DEBUG:
        return

################
################
#main
prevh=datetime.now().hour    
prev_time = 0
parse_opt(sys.argv)
config_parse()

while True:
    start_time = int(time.time())
    if DEBUG:
        print (f"{datetime.now()}; starting to read sensors", file=sys.stderr)
    try:
        if db_enabled:
            mycursor = dbconn.cursor()

        if time.time()-prev_time >= max_log_time:
            log_now=True
            prev_time = time.time()
        else:
            log_now=False

        before_furnace=-1
        after_furnace=-1
        for device_folder in glob.glob(base_dir + '28*'):
            device_file = device_folder + '/w1_slave'
            unitId,temp_c,desc=read_temp(device_file)
            now=datetime.now().strftime("%Y-%m-%d %H:%M:%S") 

            if desc=="before_furnace":
                before_furnace=temp_c
            if desc=="after_furnace":
                after_furnace=temp_c
            log_val=False

            if unitId in sensor_value:
                temp_diff=max(sensor_value[unitId])-min(sensor_value[unitId])
                if temp_diff > min_temp_diff:
                    log_val=True
            else:
                sensor_value[unitId]=[]

            sensor_value[unitId].append(temp_c)
            if len(sensor_value[unitId])>max_list_length:
                sensor_value[unitId].pop(0)

            if DEBUG:
                print(f"{datetime.now()};  Sensor 0x{unitId} ({desc}) has temperature {temp_c:5.3f}, log_now={log_now}, log_val={log_val}")

            if log_now or log_val:
                if mqtt_enabled:
                    if DEBUG:
                        print("{};   sending to mqtt".format(datetime.now()), file=sys.stderr)
                    try:
                        send_to_mqtt(unitId,desc,temp_c)
                    except:
                        print ("#send to mqtt failed: {} - {}".format(sys.exc_info()[0],sys.exc_info()[1]), file=sys.stderr)

                if db_enabled:
                    if DEBUG:
                        print("{};   sending to db".format(datetime.now()), file=sys.stderr)
                    try:
                        #print("{} - Sensor {} - {}, {:}c".format(now,unitId,desc,temp_c), file=sys.stderr)
                        mycursor.execute("INSERT IGNORE INTO TempData (td_date,td_sensor,td_temp) VALUES (%s,%s,%s)", (now,int(unitId,16),round(temp_c,2)))
                    except:
                        print ("#db operation 1 failed: {} - {}".format(sys.exc_info()[0],sys.exc_info()[1]), file=sys.stderr)

                if influx_enabled:
                    if DEBUG:
                        print("{};   sending to influx".format(datetime.now()), file=sys.stderr)
                    try:
                        send_to_influx(unitId,desc,temp_c)
                    except:
                        print ("#send to influx failed: {} - {}".format(sys.exc_info()[0],sys.exc_info()[1]), file=sys.stderr)

                #for csv file
                if outputfile:
                    try:
                        with open(outputfile, "a") as f:
                            f.write(f"{now}, {unitId}, {temp_c:5.3f}, {desc}\n")
                    except:
                        print ("#writing to {} failed: {} - {}".format(outfile,sys.exc_info()[0],sys.exc_info()[1]), file=sys.stderr)

                if desc in ('before_furnace','after_furnace'):
                    if before_furnace >0 and after_furnace>0:
                        diff=int((after_furnace-before_furnace)*100)
                        if diff>400:
                            state="Heat on"
                        elif diff <-400:
                            state="AC on"
                        else:
                            state="unknown"
                        if statefile:
                            try:
                                with open(statefile, "a") as f:
                                    f.write(f"{now},{before_furnace},{after_furnace},{diff},{state}\n")
                            except:
                                print ("#writing to {} failed: {} - {}".format(statefile,sys.exc_info()[0],sys.exc_info()[1]), file=sys.stderr)
                        if VERBOSE:
                            print(f"{now}, {before_furnace}, {after_furnace}, {diff}, {state}")

                if VERBOSE:
                    print(f"{now}, {unitId}, {temp_c:5.3f}, {desc}")
            else:
                if DEBUG:
                    print(f"{time.time()} - {prev_time} = {time.time()-prev_time}")

        if db_enabled:
            mycursor.execute("COMMIT")

    except KeyboardInterrupt:
       print("# got ^c", file=sys.stderr)
       end_program
       exit(0)

    except Exception as e:
       print("something else broke", file=sys.stderr)
       print(e, file=sys.stderr)
       print(f" unitId=0x{unitId}", file=sys.stderr)
       print(f" temp_c={temp_c}", file=sys.stderr)
       print(f" desc={desc}", file=sys.stderr)
       end_program
       exit (31)()

    #make it start over at midnight
    currh=datetime.now().hour
    if (prevh != currh):
        if currh == 0:
            try:
                end_program()
            except:
                pass
            break
        prevh=currh

    while (int(time.time())-start_time) < min_time_between_reads:
        time.sleep(1)
