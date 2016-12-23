#!/usr/bin/env python
# # -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :
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

# Unicode help: https://www.azavea.com/blog/2014/03/24/solving-unicode-problems-in-python-2-7/

# For now...
import cPickle

from datetime import datetime
from random import choice, shuffle

import predict
from spacetrack import SpaceTrackClient
import ephem

from flask import Flask, request
from flask_restful import Resource, Api
from json import dumps

import SatInfo

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

countryMapping = {
    "JPN": "Japan",
    "CIS-pre": "the Soviet Union",
    "CIS-post": "Russia",
    "US": "the United States",
    "ESA": "the European Space Agency",
    "PRC": "China",
    "FR": "France",
    "IT": "Italy",
    "ISS": "the International Space Station",
    "CA": "Canada"
}


solar_system_bodies = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]

stars = ["Vega", "Deneb", "Sirius", "Aldebaran", "Rigel", "Betelgeuse", "Capella", "Pollux", "Procyon", "Spica", "Arcturus", "Antares", "Regulus", "Altair"]

"""
Polaris the universe spins around
Never setting, just processing
"""

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

def parseQTH(qth, pypredict = True):
    qthSplit = qth.split(",")

    # pypredict uses West longitude, so make that conversion here
    if pypredict:
        qthSplit[1] = str(-1 * float(qthSplit[1]))

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

def planetsStarsAbove(qth):
    """Calculate whether certain planets or stars are visible above or not.

    Of course, it's going to be hard to see things if it's daytime!.
    """
    
    planetsStarsAbove = {}

    location = ephem.Observer()
    location.lat = qth[0]
    location.lon = qth[1]
    location.elevation = float(qth[2])


    for body in solar_system_bodies:
        e = getattr(ephem, body)

        setting = location.next_setting(e()).datetime()
        rising = location.next_rising(e()).datetime()
    
        if setting < rising:
            planetsStarsAbove[body] = True
        else:
            planetsStarsAbove[body] = False


    for star in stars:
        e = ephem.star(star)

        setting = location.next_setting(e).datetime()
        rising = location.next_rising(e).datetime()
    
        if setting < rising:
            planetsStarsAbove[star] = True
        else:
            planetsStarsAbove[star] = False

    return planetsStarsAbove

def dayOrNight(qth):
    """Calculate whether it is day or night for a given qth.

    qth needs to be in a tuple of (lat, lon, elev)
    """

    # Use of pyephem module cribbed from here:
    # https://stackoverflow.com/questions/15044521/javascript-or-python-how-do-i-figure-out-if-its-night-or-day
    user = ephem.Observer()
    user.lat = str(qth[0])
    user.lon = str(qth[1])
    """
    if qth[1] > 0:
        user.lon = "-%s" % qth[1]
    else:
        user.lon = str(qth[1])
    """
    user.elevation = float(qth[2])

    next_sunrise_datetime = user.next_rising(ephem.Sun()).datetime()
    next_sunset_datetime = user.next_setting(ephem.Sun()).datetime()

    # If it is daytime, we will see a sunset sooner than a sunrise.
    it_is_day = next_sunset_datetime < next_sunrise_datetime

    if it_is_day:
        return "day"
    else:
        return "night"

def timeAgo(launchYear):
    d = datetime.today()
    currentYear = d.strftime("%Y")
    delta = int(currentYear) - int(launchYear)

    if (delta < 10):
        return "recently"
    elif ((delta >= 10) and (delta < 25)):
        return "some time ago"
    elif (delta >= 25):
        return "a long time ago"

class SatellitesAbove(Resource):
    def get(self, qth):
        satInfo = SatInfo.SatInfo(qth = parseQTH(qth), satType = "visual-sats")

        #sats = satInfo.getSatellitesAbove(parseQTH(qth))

        return satInfo.getSatellitesAboveParsed()

class SatellitesAbovePoem(Resource):
    def get(self, qth):
        # Old Method
        #sats = getSatellitesAbove(parseQTH(qth))
        #results = parseSatellitesAboveResults(sats)

        satInfo = SatInfo.SatInfo(qth = parseQTH(qth), satType = "visual-sats")

        results = satInfo.getSatellitesAboveParsed()


        # Sort based off of elevation
        sortedIDs = sorted(results, key = lambda x: results[x]["elevation"], reverse=True)
        highestSat = results[sortedIDs[0]]

        dustPoem = generateDustPoem(highestSat)

        print highestSat

        # Get country name
        countryName = getCountryName(highestSat)

        poem = "In %s, %s left a %s orbiting the earth." % (highestSat["launch_year"], countryName, highestSat["object_type"].lower())
        poem = "%s It's above you right now." % poem
        dayNight = dayOrNight(parseQTH(qth, pypredict = False))        

        if dayNight == "day":
            poem = "%s Even though it's %s, and you can't see it." % (poem, dayNight)
        else:
            #poem = "%s Look above, carefully, for the glint of its shell. I'm going to make this super duper long so that I can test scrolling on the emulator and the device yes I will becuase scrolling has to happen automatically yes it does otherwise the text will just sit there in the screen and there won't be much that we can do about it and it'll just be cut off and there's nothing we could do no no no but this we can yes yes yes." % poem
            poem = "%s Look above, carefully, for the glint of its shell. I'm going to make this super duper long so that I can test scrolling on the emulator and the device yes I will becuase scrolling has to happen automatically" % poem
            #poem = "%s Look above, carefully, for the glint of its shell." % poem

        return generateDustPoem(highestSat)

class PlanetsStarsAbove(Resource):
    def get(self, qth):
        return planetsStarsAbove(parseQTH(qth, pypredict = False))

class PlanetsStarsAbovePoems(Resource):
    def get(self, qth):
        planets_and_stars = planetsStarsAbove(parseQTH(qth, pypredict = False))
        return generateDappledVoidPoem(planets_and_stars)


def generateDappledVoidPoem(planets_and_stars, whole = True):

    dappled_void = []
    light_options = [u"Light from", u"The shine of", u"Illumination by"]
    no_light_options = [u"No light from", u"The invisible", u"The to-be-seen-but-not-now"]
    sun_options = [u"Merged with the Sun's light. Yet.", u"Lost in the Sun's glare. Nevertheless."]


    names = planets_and_stars.keys()
    shuffle(names)

    # If the sun is out...
    if planets_and_stars["Sun"]:
        dappled_void.append(choice(sun_options))

    for name in names:
        if planets_and_stars[name]:
            if ((name == "Sun") or (name == "Moon")):
                dappled_void.append(u"%s the %s," % (choice(light_options), unicode(name)))
            else:
                dappled_void.append(u"%s %s," % (choice(light_options), unicode(name)))

        else:
            dappled_void.append(u"%s %s," % (choice(no_light_options), unicode(name)))

    dappled_void[-1] = dappled_void[-1].rstrip(",")
    dappled_void[-1] = u"%s." % dappled_void[-1]

    if whole:
        dappledVoidPoem = unicode("\n\n".join(dappled_void))
        return {"dappled_void_title": u"Dappled Void (after Anne Carson)".encode("utf-8"), "dappled_void_poem": dappledVoidPoem.encode("utf-8")}
    else:
        encodedDappledVoidPoem = []
        for line in dappled_void:
            encodedDappledVoidPoem.append(line.encode("utf-8"))
        return {"dappled_void_title": u"Dappled Void (after Anne Carson)".encode("utf-8"), "dappled_void_poem": encodedDappledVoidPoem}

def generateDustPoem(satInfo, whole = True):
    """
(The earth | She) drags the (object type) back to the (surface | ground | crust)
(Remember | Forget | Recall | Understand) its name, "(sat name)"
(Hurled | Thrown | Launched) to the heavens upon fire (a while a go | a long time ago | recently)
It will be reduced to dust.
"""
    subjects = [u"The earth", u"The Field", u"She", u"Friction", u"The \u00E6ther"]
    actions = [u"drags", u"attracts", u"slows", u"decays"]
    surfaces = [u"surface", u"ground", u"crust", u"atmosphere", u"cloudtops"]
    remembers = [u"Remember", u"Forget", u"Recall", u"Understand", u"Know", u"Wonder about", u"Question"]
    hurleds = [u"Hurled", u"Thrown", u"Launched", u"Propelled", u"Thrust"]
    endings = [u"It will be reduced to dust.", u"It will remain aloft, forever.", u"It will be jostled by the solar wind.", u"It tumbles and tumbles, incessantly.", u"It will remain, still, in the cold void."]
    time = timeAgo(satInfo["launch_year"])

    dustPoemLines = []

    dustPoemLines.append(u"EL %d DEGREES" % (int(round(float(satInfo["elevation"])))))
    dustPoemLines.append(u"%s %s the %s above the %s" % (choice(subjects), choice(actions), satInfo["object_type"].lower(), choice(surfaces)))
    dustPoemLines.append(u"%s its name, \u201C%s\u201D" % (choice(remembers), satInfo["satname"]))
    dustPoemLines.append(u"%s to the heavens upon fire %s" % (choice(hurleds), time))
    dustPoemLines.append(choice(endings))

    """
    dustPoem = "EL %d DEGREES\n\n" % (int(round(float(satInfo["elevation"]))))
    dustPoem = "%s%s drags the %s back to the %s\n\n" % (dustPoem, choice(subjects), satInfo["object_type"].lower(), choice(surfaces))
    dustPoem = "%s%s its name, \"%s\"\n\n" % (dustPoem, choice(remembers), satInfo["satname"])
    dustPoem = "%s%s to the heavens upon fire %s\n\n" % (dustPoem, choice(hurleds), time)
    dustPoem = "%sIt will be reduced to dust." % (dustPoem)
    """

    if whole:
        dustPoem = unicode("\n\n".join(dustPoemLines[1:]))
        print dustPoem.encode("utf-8") 
        #dustPoem = dustPoemLines[0]
        return {"title": dustPoemLines[0].encode("utf-8"), "poem": dustPoem.encode("utf-8")}
    else:
        encodedDustPoem = []
        for line in dustPoemLines[1:]:
            encodedDustPoem.append(line.encode("utf-8"))
        return {"title": dustPoemLines[0].encode("utf-8"), "poem": encodedDustPoem}

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
api.add_resource(PlanetsStarsAbove, "/planets_stars/pebble/<string:qth>")
api.add_resource(PlanetsStarsAbovePoems, "/planets_stars/pebble/poem/<string:qth>")

if __name__ == "__main__":
    #application.run(host="0.0.0.0")
    application.run(host="127.0.0.1",port=34567)
