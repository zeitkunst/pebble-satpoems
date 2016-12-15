#!/usr/bin/env python
"""
Things that could be included: sat name, ID, object type, country, launch year, visibility, elevation

(The earth | She) drags the (object type) back to the (surface | ground | crust)
(Remember | Forget | Recall | Understand) its name, "(sat name)"
(Hurled | Thrown | Launched) to the heavens upon fire (a while a go | a long time ago | recently)
It will be reduced to dust.


In the darkness
(In the | During the ) ((darkness | night | void) | (day | light))
a (object) from (countryName) is above, (visible | invisible, but present)
From (a while a go| a long time ago | recently)
"""
# For now...
import cPickle

from datetime import datetime
from random import choice

import predict
from spacetrack import SpaceTrackClient
import ephem

from flask import Flask, request
from flask_restful import Resource, Api
from json import dumps

"""
Methods, things we need:

    * Update TLEs; check memcached first, if there, retrieve, if not, get updated values and save in memcached
    * Chunk these updates, write cron job to do so
    * Abstract out checking whether or not a satellite is above
    * Method for checking a QTH against different sets of satellites
    * Method for periodically saving a set of values from memcached to local storage in pickled files
"""

application = Flask(__name__)
api = Api(application)

homeQTH = (42.294615, 71.302342, 185)

countryMapping = {
    "JPN": "Japan",
    "CIS-pre": "the Soviet Union",
    "CIS-post": "Russia",
    "US": "the United States",
    "ESA": "the European Space Agency",
    "PRC": "China",
    "FR": "France",
    "IT": "Italy",
    "ISS": "the International Space Station"
}

objectMapping = {
    "R/B": "rocket booster"
}

with open("satelliteData.pickle", "rb") as f:
    satData = cPickle.load(f)

def parseSatellitesAboveResults(sats):
    # Create our json result
    result = {}
    for key in sats.keys():
        result[key] = {
            "elevation": sats[key]["prediction"]["elevation"],
            "visibility": sats[key]["prediction"]["visibility"],
            "geostationary": sats[key]["prediction"]["geostationary"],
            "satname": sats[key]["catalogInfo"][0]["SATNAME"],
            "object_type": sats[key]["catalogInfo"][0]["OBJECT_TYPE"],
            "country": sats[key]["catalogInfo"][0]["COUNTRY"],
            "launch_year": sats[key]["catalogInfo"][0]["LAUNCH_YEAR"],
            "launch": sats[key]["catalogInfo"][0]["LAUNCH"]

        }

    return result

def parseQTH(qth):
    qthSplit = qth.split(",")
        
    if (len(qthSplit) == 2):
        # Assume 1000ft for elevation if non given
        return (qthSplit[0], qthSplit[1], 1000)
    else:
        return (qthSplit[0], qthSplit[1], qthSplit[2])

def getCountryName(satInfo):
    if satInfo["country"] == "CIS":
        if satInfo["launch_year"] <= "1989":
            return countryMapping["CIS-pre"]
        else:
            return countryMapping["CIS-post"]
    else:
        return countryMapping[satInfo["country"]]

def dayOrNight(qth):
    """Calculate whether it is day or night for a given qth.

    qth needs to be in a tuple of (lat, lon, elev) (with lon as W)
    """

    # Use of pyephem module cribbed from here:
    # https://stackoverflow.com/questions/15044521/javascript-or-python-how-do-i-figure-out-if-its-night-or-day
    user = ephem.Observer()
    user.lat = str(qth[0])
    if qth[1] > 0:
        user.lon = "-%s" % qth[1]
    else:
        user.lon = str(qth[1])
    user.elevation = float(qth[2])

    next_sunrise_datetime = user.next_rising(ephem.Sun()).datetime()
    next_sunset_datetime = user.next_setting(ephem.Sun()).datetime()

    # If it is daytime, we will see a sunset sooner than a sunrise.
    it_is_day = next_sunset_datetime < next_sunrise_datetime

    if it_is_day:
        return "daytime"
    else:
        return "night"

def timeAgo(launchYear):
    d = datetime.today()
    currentYear = d.strftime("%Y")
    delta = int(currentYear) - int(launchYear)

    if (delta < 10):
        return "recently"
    elif ((delta >= 10) and (delta < 25)):
        return "a while ago"
    elif (delta >= 25):
        return "a long time ago"
class SatellitesAbove(Resource):
    def get(self, qth):
        
        sats = getSatellitesAbove(parseQTH(qth))

        return parseSatellitesAboveResults(sats)

class SatellitesAbovePoem(Resource):
    def get(self, qth):
        sats = getSatellitesAbove(parseQTH(qth))

        results = parseSatellitesAboveResults(sats)

        # Sort based off of elevation
        sortedIDs = sorted(results, key = lambda x: results[x]["elevation"], reverse=True)
        highestSat = results[sortedIDs[0]]

        dustPoem = generateDustPoem(highestSat)

        print highestSat

        # Get country name
        countryName = getCountryName(highestSat)

        poem = "In %s, %s left a %s orbiting the earth." % (highestSat["launch_year"], countryName, highestSat["object_type"].lower())
        poem = "%s It's above you right now." % poem
        dayNight = dayOrNight(parseQTH(qth))        

        if dayNight == "daytime":
            poem = "%s Even though it's %s, and you can't see it." % (poem, dayNight)
        else:
            #poem = "%s Look above, carefully, for the glint of its shell. I'm going to make this super duper long so that I can test scrolling on the emulator and the device yes I will becuase scrolling has to happen automatically yes it does otherwise the text will just sit there in the screen and there won't be much that we can do about it and it'll just be cut off and there's nothing we could do no no no but this we can yes yes yes." % poem
            poem = "%s Look above, carefully, for the glint of its shell. I'm going to make this super duper long so that I can test scrolling on the emulator and the device yes I will becuase scrolling has to happen automatically" % poem
            #poem = "%s Look above, carefully, for the glint of its shell." % poem

        return {"poem": generateDustPoem(highestSat)}

def generateDustPoem(satInfo):
    """
(The earth | She) drags the (object type) back to the (surface | ground | crust)
(Remember | Forget | Recall | Understand) its name, "(sat name)"
(Hurled | Thrown | Launched) to the heavens upon fire (a while a go | a long time ago | recently)
It will be reduced to dust.
"""
    subjects = ["The earth", "She"]
    surfaces = ["surface", "ground", "crust"]
    remembers = ["Remember", "Forget", "Recall", "Understand"]
    hurleds = ["Hurled", "Thrown", "Launched"]
    time = timeAgo(satInfo["launch_year"])

    dustPoem = "EL %d DEGREES\n\n" % (int(round(float(satInfo["elevation"]))))
    dustPoem = "%s%s drags the %s back to the %s\n\n" % (dustPoem, choice(subjects), satInfo["object_type"].lower(), choice(surfaces))
    dustPoem = "%s%s its name, \"%s\"\n\n" % (dustPoem, choice(remembers), satInfo["satname"])
    dustPoem = "%s%s to the heavens upon fire %s\n\n" % (dustPoem, choice(hurleds), time)
    dustPoem = "%sIt will be reduced to dust." % (dustPoem)

    return dustPoem

def getSatellitesAbove(qth):
    sats = {}

    for ID in satData.keys():
        data = satData[ID]
        currentTLE = data["tle"]
        currentTLE = currentTLE.split("\n")
        currentTLE.pop()
        tle = "%s\n%s\n%s" % (data["catalogInfo"][0]["SATNAME"], currentTLE[0], currentTLE[1])
        p = predict.observe(tle, qth)
    
        # This just gets me things above the horizon, not things actually visible
        if p["elevation"] > 0:
            #print "%s\nObject Type: %s\nNORAD ID: %s\nElevation: %s\nVisible: %s\n" % (p["name"],satData[ID]["catalogInfo"][0]["OBJECT_TYPE"], ID, p["elevation"], p["visibility"])
            resultData = data
            resultData["prediction"] = p
            sats[ID] = resultData

    return sats

api.add_resource(SatellitesAbove, "/sats/pebble/<string:qth>")
api.add_resource(SatellitesAbovePoem, "/sats/pebble/poem/<string:qth>")

if __name__ == "__main__":
    #application.run(host="0.0.0.0")
    application.run(host="127.0.0.1",port=34567)
