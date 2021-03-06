# ------------------------------------------#
# Import the Requests

import requests # To make REST requests of the client.
import time
import os.path
import rsa # To decrypt values.
import csv # To write the data into CSV file safely
import binascii
import logging
import logging.config
import yaml
import pickle
import glob
import os
from cliff.command import Command
import json

# ------------------------------------------#
# Load the Configuration file
SERVER_CONFIG = 'config/server.config'



# Set up logging config files
logging.config.dictConfig(yaml.load(open('config/recovery_log.config', 'r')))

# export Readme file

def readMe(scaleName,data_file,fileList,deleteable,entryNo,error,config):
    log = logging.getLogger(__name__)
    export = config["PATH"]+"recovered_data/" + "README_" + scaleName + "_recovered_" + time.strftime(config["DATE_FORMAT"]) +'.txt'
    readme = open(export,"w")
    readme.write("Data recovery done at %s, %s for %s questionnaire. Recovery information are as follow:\n" % (time.strftime(config["TIME_FORMAT"]), time.strftime(config["DATE_FORMAT"]), scaleName));
    readme.write("\n");
    readme.write("\t%d data files found in raw_data folder:\n\t\tStart file: %s\n\t\tEnd file: %s\n" % (len(fileList),fileList[0],fileList[-1]));
    readme.write("\t%d data entry recovered, %d error in recovery. HEADUP: There might be duplication in entries.\n" % (entryNo,error));
    readme.write("\tRecovered data file path: %s\n" % data_file);
    readme.write("\n");
    if not deleteable:
        readme.write("*****WARNING******: This questionnaire is not deleteable on the server. Make sure that you only recovered the most recent raw data file otherwise you might have high amount of duplicated data.\n");
        readme.write("*****WARNING******: For undeletable questionnaire, active dataset is a more acurrate and completed dataset than recovered dataset.\n");
    readme.close()



# Decrypting

def decrypt(crypto, id, scaleName, field,config):
    log = logging.getLogger(__name__)
    with open(config["PRIVATE_FILE"]) as privatefile:
        keydata = privatefile.read()
    priv_key = rsa.PrivateKey.load_pkcs1(keydata)
    if crypto is None: return ""
    try:
        value = crypto.decode('base64')
        log.info('Decode successfully.')
        try:
            message = rsa.decrypt(value, priv_key)
            log.info('Decrypt successfully.')
            return message.decode('utf8')
        except (rsa.pkcs1.CryptoError, rsa.pkcs1.DecryptionError):
            log.error('Decrypt failed, original value recorded. Questionnaire = %s, Entry ID: %s, Field: %s See information:', scaleName, id, field, exc_info = 1)
            return crypto
    except (UnicodeDecodeError, binascii.Error):
        log.error('Decode failed, item skipped. Questionnaire = %s, Entry ID: %s, Field: %s See information:', scaleName, id, field, exc_info = 1)

# Create data files with date as name:
def createFile(file, ks):
    log = logging.getLogger(__name__)
    if not os.path.exists(file): # Create new file if file doesn't exist
        with open(file, 'w') as datacsv:
            headerwriter = csv.DictWriter(datacsv, dialect='excel', fieldnames= ks)
            try:
                headerwriter.writeheader()
                log.info("New data file created: %s", file)
            except csv.Error:
                log.critcal("Failed to create new data files, fatal, emailed admin.", exc_info=1)

# SafeWrite function, use this to write questionnaire data into csv files
def safeWrite(quest, date_file, scaleName, deleteable, config):
#B\ Open [form_name]_[date].csv, append the data we have into it, one by one.
    log = logging.getLogger(__name__)
    log.info("Writing new entries from %s to %s: writing in progress......", scaleName, date_file)
    ks = list(quest[0].keys())
    ks.sort()
    createFile(date_file, ks)
    with open(date_file, 'a') as datacsv:
        dataWriter = csv.DictWriter(datacsv, dialect='excel', fieldnames= ks)
        t = 0
        error = 0
        for entry in quest:
            for key in ks:
                if(key.endswith("RSA")): value = decrypt(entry[key], entry['id'], scaleName, key, config)
                elif entry[key] is None: value = ""
                elif isinstance(entry[key], unicode): value = entry[key]
                else:
                    try:
                        value = str(entry[key]) # could be an int, make sure it is a string so we can encode it.
                    except:
                        log.error("Data encode failed, data lost. Questionnaire: %s, Entry ID: %s, Field: %s", scaleName, entry['id'], key, exc_info = 1) # Should log error, entry ID and data field
                if (value != None):
                    try:
                        entry[key] = value.encode('utf-8')
                        log.debug("Data successfully encoded.")
                    except UnicodeEncodeError:
                        log.error("Data encode failed, data lost. Questionnaire: %s, Entry ID: %s, Field: %s", scaleName, entry['id'], key, exc_info = 1) # Should log error, entry ID and data field
                else: entry[key] = ""
            try:
                dataWriter.writerow(entry)
                t += 1
                log.debug("%s entries wrote successfully.", str(t))
            except csv.Error:
                error += 1
                log.critical("Failed in writing entry, Questionnaire: %s, Entry ID: %s", scaleName, str(entry['id']), exc_info = 1)
        log.info("Questionnaire %s update finished - %s new entries recoded successfully.", scaleName, str(t))
        if error > 0:
            log.critical("Questionnaire %s update error - %s new entries failed to recode.", scaleName, str(error))
    return (t, error)

# Check the path before doing anything
def pathCheck(config):
    log = logging.getLogger(__name__)
    if not os.path.exists(config["PATH"]+"raw_data/"):
        log.error("No raw_data folder is found, please double check before continuing.")
        print("No raw_data folder is found, please double check before continuing.")
        return False
    if not os.path.exists(config["PATH"]+"recovered_data/"):
        try:
            os.makedirs(config["PATH"]+"recovered_data/")
            log.info("Successfully created recoverer_data folder.")
            return True
        except:
            log.critical("Failed to create data folders, fatal, emailed admin.", exc_info=1)
            return False
    else: return True

# Read in files here and recover the data
def safeRecover(scaleName,deleteable,config):
    log = logging.getLogger(__name__)
    fileList = sorted(glob.glob(config["PATH"]+'raw_data/'+scaleName+'*.json'))
    newest = max(glob.iglob(config["PATH"]+'raw_data/'+scaleName+'*.json'), key=os.path.getctime)
    entryNo = 0
    error = 0
    data_file = config["PATH"]+"active_data/" + scaleName + "_recovered_" + time.strftime(config["DATE_FORMAT"]) +'.csv'
    try:
        if deleteable:
            for infile in fileList:
                with open(infile) as json_file:
                    response = json.load(json_file)
                    t, e = safeWrite(response,data_file,scaleName,deleteable,config)
                    entryNo += t
                    error += e
        else:
            with open(newest) as json_file:
                response = json.load(json_file)
                t, e = safeWrite(response,data_file,scaleName,deleteable,config)
                entryNo += t
                error += e
        readMe(scaleName,data_file,fileList,deleteable,entryNo,error,config)
        log.info("Successfully recover scale %s.",scaleName)
        return True
    except:
        log.critical("Failed to recover scale %s. emailed admin.",scaleName,exc_info=1)
        return False


# Take your order so that we know what scale and how much data you want to recover:
def takeOrder(scaleName,config):
    log = logging.getLogger(__name__)
    benchMark = {}
    # Read in benchMark information
    try:
        with open(config["PATH"]+'active_data/benchMark.json',"rb") as benchMarkJson:
            benchMark = json.load(benchMarkJson)
        log.info("benchMark information successfully retrived.")
    except:
        log.critical("benchMark information retrived failed, immediate attention needed. Detail:\n", exc_info = 1)
    s = 0
    if scaleName == '.':
        for scale in benchMark.keys():
# Decode all the scales:
            if safeRecover(scale,benchMark[scale]['deleteable'],config): s+=1
    elif (scaleName in benchMark.keys()):
        if safeRecover(scaleName,benchMark[scaleName]['deleteable'],config): s+=1
        log.info("Scale %s is found and data are collected.", scaleName)
    else:
        log.info("Scale name is not correct, please check.")

    log.info("Database recovery finished: %s questionnaires' data recovered.", str(s))



# ------------------------------------------#
# This is the main module
def recovery(scaleName,config):
    log = logging.getLogger(__name__)
    if pathCheck(config):
        log.info("Data Recovery tried at %s, %s",time.strftime(config["DATE_FORMAT"]), time.strftime(config["TIME_FORMAT"]))
        takeOrder(scaleName,config)
    else:
        log.info("No raw data found or recovery data folder failed to be created. Please check before trying again. Thanks!")


# This is a over all program
def martin(task_list,serverName,scaleName):
    log = logging.getLogger('martin')
    try:
        address = yaml.load(open(task_list, 'r'))
        log.info('Address book read successfully.')
    except:
        log.critical('Address book read failed. Emailed admin.', exc_info=1)
    if serverName == '.':
        for key in address:
            config = address[key]
            log.info('Server for decode: %s. Ready?: %s',str(key),str(config['READY']))
            if config['READY']: recovery(scaleName,config)
    elif (serverName in address.keys()):
        config = address[serverName]
        log.info('Address for decode: %s. Ready?: %s(Ready Checked is overwrited).',str(serverName),str(config['READY']))
        recovery(scaleName,config)
    else:
        log.info("Server name is not correct, please check.")

# Make it a command line

class Decode(Command):
    "Command for recovering active data from raw data."

    log = logging.getLogger(__name__)

    def get_parser(self, prog_name):
        parser = super(Decode, self).get_parser(prog_name)
        parser.add_argument('serverName', nargs='?', default='.')
        parser.add_argument('scaleName', nargs='?', default='.')
        return parser

    def take_action(self, parsed_args):
        self.log.info('sending greeting')
        self.log.debug('debugging')
        martin(SERVER_CONFIG,parsed_args.serverName,parsed_args.scaleName)

class Error(Command):
    "Always raises an error"

    log = logging.getLogger(__name__)

    def take_action(self, parsed_args):
        self.log.info('causing error')
        raise RuntimeError('this is the expected exception')
