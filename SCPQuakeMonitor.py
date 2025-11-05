# -*- coding: utf-8 -*-
"""
Created on Mon Jul  8 13:24:25 2024
Updated 10/31/25
Notes:
Subporcess.run is preferred to subprocess.call or os.system, but requires python 3.5+
Description:
Checks USGS website for relevant earthquakes and adds them to SeisComP database.
Also, send an email for specified facilities when criteria is met
@author: QuakePanda
"""

import logging
import os
import pandas as pd
import smtplib
import subprocess
import time

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from jinja2 import Template
from obspy import read_events
from obspy.geodetics.base import gps2dist_azimuth

scwf_folder = os.path.normpath('/data/seiscomp/waveforms')
quake_folder = os.path.normpath('/data/seiscomp/quakes')
SDS_path = os.path.normpath('/data/seiscomp/archive')
email_template = os.path.normpath('/opt/seiscomp/lib/FacEmailTemplate.html')
dwr_logo = os.path.normpath('/opt/seiscomp/lib/example.png')

QuakeML_URL = ("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_hour.quakeml")
INCLUDE_LIST = ['ci','nc','nn','uw']

Log_Format = "%(levelname)s %(asctime)s - %(message)s"
logging.basicConfig(filename="SCPQuakeMonitor.log", filemode="a", level=logging.INFO, format=Log_Format)

# Send an HTML email with an embedded image and a plain text message for
# email clients that don't want to display the HTML.
# Define these once; use them twice!
strFrom = 'example@email.com'
recipients = ['example1@email.com', 'example2@email.com'] 
emaillist = [elem.strip().split(',') for elem in recipients]
smtpserver = 'your.mail.host.com'
smtpport = 22

# Dictionary (Lookup table) with lat/long of facilities
Facilties = {"Example Facility 1": [37.12345,-121.12345],
             "Example Facility 2": [37.0123,-121.0123],
             "Example Facility 3": [36.98765,-120.98765]
             }

def send_email(email_data, evid):
    # String for message subject
    subject = 'Example EQ Alert'
    # Create the root message and fill in the from, to, and subject headers
    msgRoot = MIMEMultipart('related')
    msgRoot['Subject'] = subject
    msgRoot['From'] = strFrom
    msgRoot['To'] = ", ".join(recipients)
    msgRoot.preamble = 'This is a multi-part message in MIME format.'
    
    # Encapsulate the plain and HTML versions of the message body in an
    # 'alternative' part, so message agents can decide which they want to display.
    msgAlternative = MIMEMultipart('alternative')
    msgRoot.attach(msgAlternative)
    msgText = MIMEText('This is the alternative plain text message.')
    msgAlternative.attach(msgText)
    
    with open(email_template, "r") as file:
        template_str = file.read()
    print(template_str)
    jinja_template = Template(template_str)
    email_content = jinja_template.render(email_data)
    print(email_content)
    msgText = MIMEText(email_content, 'html')
    msgAlternative.attach(msgText)
    
    # Define the image's ID as referenced in template and embed
    fp = open(dwr_logo, 'rb')
    msgImage = MIMEImage(fp.read())
    fp.close()
    msgImage.add_header('Content-ID', '<dwr_logo>')
    msgRoot.attach(msgImage)
    
    # Send the email
    smtp = smtplib.SMTP(smtpserver, smtpport)
    smtp.sendmail(strFrom, emaillist, msgRoot.as_string())
    smtp.quit()

def main():
    logging.debug("Reading QuakeML from %s" % QuakeML_URL)
    cat = read_events(QuakeML_URL)
    logging.debug(cat)
    for event in cat:
        info = event.creation_info
        agid = info.get('agency_id')
        if agid in INCLUDE_LIST:
            res_id = event.resource_id.id
            qml_id = res_id.rsplit('/', 1)[-1]
            evid = qml_id.split('.', 1)[0]
            xml_file = evid + '.xml'
            origin = event.preferred_origin()
            et = origin.time.strftime('%Y%m%d%H%M%S')
            xml_path = os.path.join(scwf_folder, et, xml_file)
            xml_dir = os.path.join(scwf_folder, et)
            if not os.path.exists(xml_dir):
                os.makedirs(xml_dir)
                logging.info("created folder : ", xml_dir)
            if os.path.isfile(xml_path):
                logging.debug("%s file already exists" % xml_file)
            else:
                logging.info("Creating and dispatching %s" % xml_file)
                # Add the earthquake to the SeisComP database
                try:
                    event.resource_id = evid
                    event.write(xml_path, format='SC3ML')
                    time.sleep(5)
                    #add_event = '/opt/seiscomp/seiscomp_6.4.3/bin/scdispatch -i ' + xml_path
                    subprocess.run(["/opt/seiscomp/seiscomp_6.4.3/bin/scdb", "-i", xml_path])
                    # Subprocess waits for command to finish before proceeding
                    logging.info("Finished dispatching %s" % xml_path)
                except Exception as error:
                    logging.exception("Failed to create and dispatch {0}!\n".format(str(xml_path)))
                finally:
                    pass
                # Send an email if certain magnitude-distance criteria are met
                try:
                    evla = event.preferred_origin().latitude
                    evlo = event.preferred_origin().longitude
                    evtime = event.preferred_origin().time
                    evmag = event.preferred_magnitude().mag
                    facs = [*Facilties.values()]
                    sites = {}
                    if 3.95 <= evmag < 4.95:
                        for key, val in facs.items():
                            epidist = gps2dist_azimuth(val[0], val[1], evla, evlo)
                            # check if event within 71 km
                            if epidist[0] < 71000:
                                sites['Dam'] = key
                                sites['Distance (km)'] = epidist/1000
                    elif 4.95 <= evmag < 5.95:
                        for key, val in facs.items():
                            epidist = gps2dist_azimuth(val[0], val[1], evla, evlo)
                            # check if event within 118 km
                            if epidist[0] < 118000:
                                sites['Dam'] = key
                                sites['Distance (km)'] = epidist/1000
                    elif 5.95 <= evmag < 6.95:
                        for key, val in facs.items():
                            epidist = gps2dist_azimuth(val[0], val[1], evla, evlo)
                            # check if event within 221 km
                            if epidist[0] < 221000:
                                sites['Dam'] = key
                                sites['Distance (km)'] = epidist/1000
                    elif 6.95 <= evmag < 7.95:
                        for key, val in facs.items():
                            epidist = gps2dist_azimuth(val[0], val[1], evla, evlo)
                            # check if event within 420 km
                            if epidist[0] < 420000:
                                sites['Dam'] = key
                                sites['Distance (km)'] = epidist/1000
                    elif evmag >= 7.95:
                        for key, val in facs.items():
                            epidist = gps2dist_azimuth(val[0], val[1], evla, evlo)
                            # check if event within 750 km
                            if epidist[0] < 750000:
                                sites['Dam'] = key
                                sites['Distance (km)'] = epidist/1000
                    if len(sites) > 0:
                        # send email
                        df = pd.json_normalize(sites)
                        df.sort_values('Distance (km)')
                        print(df)
                        table = df.to_html(index=True, header=True)
                        email_data = {
                            "evid": evid,
                            "evtime": evtime,
                            "evmag": evmag,
                            "latitude": evla,
                            "longitude": evlo,
                            "table": table
                            }
                        send_email(email_data, evid)
                except Exception as error:
                    logging.exception("Failed to calculate facility EQ criteria for {0}!\n".format(str(xml_path)))
                finally:
                    pass

if __name__=="__main__":
    main()