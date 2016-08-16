#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__    = 'Ben Jones <ben.jones12()gmail.com>'
__copyright__ = 'Copyright 2014 Ben Jones'
__license__   = """Eclipse Public License - v 1.0 (http://www.eclipse.org/legal/epl-v10.html)"""

import paho.mqtt.client as mqtt
import xml.etree.ElementTree as xml
import atexit
import logging
import requests
import socket
import sys

from time import sleep
from apscheduler.schedulers.background import BackgroundScheduler

# request properties
enasolarhost = 'http://enasolar'
enasolartimeout = 2

# MQTT connection properties
broker = 'localhost'
port = 1883
username = 'enasolar'
password = 'password'
lwttopic = '/clients/enasolar'
topic = '/enasolar/'

# logging properties
logfile = 'enasolar.log'
loglevel = 'WARN'
logformat = '%(asctime)-15s %(levelname)-5s [%(module)s] %(message)s'

# initialise logging
logging.basicConfig(filename=logfile, level=loglevel, format=logformat)
logging.info("Starting EnaSolar monitor")
logging.info("INFO MODE")
logging.debug("DEBUG MODE")

# initialise MQTT broker connection
mqttc = mqtt.Client('enasolar', clean_session=True)

# initialise scheduler
sched = BackgroundScheduler()
sched.start()
atexit.register(lambda: sched.shutdown(wait=False))

def on_connect(client, userdata, rc):
    if (rc == 0):
        logging.debug("Successfully connected to MQTT broker")
        mqttc.publish(lwttopic, '1', qos=0, retain=True)
    elif result_code == 1:
        logging.info("Connection refused - unacceptable protocol version")
    elif result_code == 2:
        logging.info("Connection refused - identifier rejected")
    elif result_code == 3:
        logging.info("Connection refused - server unavailable")
    elif result_code == 4:
        logging.info("Connection refused - bad user name or password")
    elif result_code == 5:
        logging.info("Connection refused - not authorised")
    else:
        logging.warning("Connection failed - result code %d" % (result_code))

def on_disconnect(mosq, userdata, result_code):
    if result_code == 0:
        logging.info("Clean disconnection from MQTT broker")
    else:
        logging.info("Connection to MQTT broker lost. Will attempt to reconnect in 5s...")
        sleep(5)

def connect_mqtt():
    logging.debug("Attempting connection to MQTT broker %s:%d..." % (broker, port))
    mqttc.on_connect = on_connect
    mqttc.on_disconnect = on_disconnect
    mqttc.username_pw_set(username, password)
    mqttc.will_set(lwttopic, '0', qos=0, retain=True)
    try:
        mqttc.connect(broker, port, 60)
    except Exception, e:
        logging.error("Cannot connect to MQTT broker at %s:%d: %s" % (broker, port, str(e)))
        sys.exit(2)

    while True:
        try:
            mqttc.loop_forever()
        except socket.error:
            logging.info("MQTT server disconnected. Sleeping...")
            sleep(5)
        except:
            break

def publish_data(name, data):
    # send update to our MQTT topic
    mqttc.publish(topic + name, str(data), qos=0, retain=False)

def request_xml(url):
    # send a GET request to the EnaSolar inverter
    try:
        response = requests.get(url, timeout=enasolartimeout)
        if (response.status_code is not 200):
            logging.error("Invalid response received: %d" % (response.status_code))
            return
    except requests.exceptions.Timeout, e:
        logging.warn("Request timed out, skipping")
        return
    except Exception, e:
        logging.error("Error executing request: %s" % (str(e)))
        return

    # remove the BOM preamble
    utf8 = response.text.encode('utf-8')
    ascii = utf8.decode('ascii', 'ignore')

    if not ascii:
        return None

    # parse the XML and return
    root = xml.fromstring(ascii)
    return root

def request_meters():
    root = request_xml("%s/meters.xml" % (enasolarhost))

    if root is None:
        logging.warn("Request for meters.xml returned nothing, skipping")
        return

    for child in root:
        if (child.tag == 'OutputPower'):
            power = float(child.text)
            publish_data('outputpower', power)

def request_data():
    root = request_xml("%s/data.xml" % (enasolarhost))

    if root is None:
        logging.warn("Request for data.xml returned nothing, skipping")
        return

    for child in root:
        if (child.tag == 'EnergyToday'):
            today = float(int(child.text, 16)) / 100
            publish_data('energytoday', today)

        if (child.tag == 'EnergyYesterday'):
            yesterday = float(int(child.text, 16)) / 100
            publish_data('energyyesterday', yesterday)

        if (child.tag == 'EnergyLifetime'):
            lifetime = float(int(child.text, 16)) / 100
            publish_data('energylifetime', lifetime)

        if (child.tag == 'DaysProducing'):
            days = int(child.text, 16)
            publish_data('daysproducing', days)

if __name__ == "__main__":

    sched.add_job(request_meters, 'interval', seconds=5)
    sched.add_job(request_data, 'interval', minutes=5)

    connect_mqtt()
