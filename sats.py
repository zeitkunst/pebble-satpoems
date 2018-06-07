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
import os, time

import predict
from spacetrack import SpaceTrackClient
import ephem, ephem.stars


from flask import Flask, request
from flask_restful import Resource, Api
import json

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

#stars = ["Vega", "Deneb", "Sirius", "Aldebaran", "Rigel", "Betelgeuse", "Capella", "Castor", "Pollux", "Procyon", "Spica", "Arcturus", "Antares", "Regulus", "Altair", "Polaris", "Mizar"]
stars = ["Vega", "Deneb", "Sirius", "Aldebaran", "Rigel", "Betelgeuse", "Capella", "Castor", "Pollux", "Procyon", "Spica", "Arcturus", "Antares", "Regulus", "Altair", "Albereo"]

#stars_expanded = ["Vega", "Deneb", "Sirius", "Aldebaran", "Rigel", "Betelgeuse", "Capella", "Castor", "Pollux", "Procyon", "Spica", "Arcturus", "Antares", "Regulus", "Altair", "Polaris", "Mizar", "TRAPPIST-1", "KEPPLER-22"]

stars_expanded_distances = {
    "Vega": 25.04,
    "Deneb": 2615,
    "Sirius": 8.60,
    "Aldebaran": 65.3,
    "Rigel": 860,
    "Betelgeuse": 643,
    "Capella": 42.919,
    "Pollux": 33.78,
    "Castor": 51,
    "Procyon": 11.46,
    "Spica": 250,
    "Arcturus": 36.7,
    "Antares": 550,
    "Regulus": 79.3,
    "Altair": 16.73,
    "Polaris": 323,
    "Mizar": 86,
    "Albereo": 430,
    "TRAPPIST-1": 39.5,
    "KEPPLER-22": 620
}

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
        

        satPoem = generateSatPoem(highestSat, qth = parseQTH(qth))

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

        return generateSatPoem(highestSat)

# TODO
# Refactor so that we don't have so much overlap between these methods
class SatellitesAbovePoemOffset(Resource):
    def get(self, qth, offset):
        # Old Method
        #sats = getSatellitesAbove(parseQTH(qth))
        #results = parseSatellitesAboveResults(sats)
        offset = int(offset)
        print "OFFSET: %s" % offset

        satInfo = SatInfo.SatInfo(qth = parseQTH(qth), satType = "visual-sats", offset = offset)

        results = satInfo.getSatellitesAboveParsed()


        # Sort based off of elevation
        sortedIDs = sorted(results, key = lambda x: results[x]["elevation"], reverse=True)
        highestSat = results[sortedIDs[0]]

        satPoem = generateSatPoem(highestSat, qth = qth)

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

        poem = generateSatPoem(highestSat)
        poemSave = poem
        poemSave["qth"] = parseQTH(qth, pypredict = False)
        poemSave["offset"] = offset
        poemSave["time"] = time.time()
        filename = "satellite_%d.json" % int(round(poemSave["time"]))
        with open(os.path.join("poems", filename), 'w') as f:
            f.write(json.dumps(poemSave))
        return poem


class PlanetsStarsAbove(Resource):
    def get(self, qth):
        return planetsStarsAbove(parseQTH(qth, pypredict = False))

class PlanetsStarsAbovePoems(Resource):
    def get(self, qth):
        planets_and_stars = planetsStarsAbove(parseQTH(qth, pypredict = False))
        return generateDappledVoidPoem(planets_and_stars)

class PlanetsStarsEveryMoment(Resource):
    def get(self, qth):
        return planetsStarsAbove(parseQTH(qth, pypredict = False))

class PlanetsStarsEveryMomentPoems(Resource):
    def get(self, qth):

        planets_and_stars = planetsStarsAbove(parseQTH(qth, pypredict = False))
        return generateEveryMomentPoem(qth, planets_and_stars)

def generateEveryMomentPoem(qth, planets_and_stars, whole = True):

    every_moment = []
    YEAR_THRESHOLD = 65
    opening_options = [
        u"TIME NOW IS TIME PAST",
        u"A STAR TOUCHES YOU",
        u"THE SPECTRUM REACHES YOU",
        u"WHAT ARE YOU NOW",
        u"WHEN ENDS YOUR PAST"
    ]
    no_light_options = [
        u"IN THE GLARE IS %s",
        u"HIDDEN IS %s",
        u"%s IS THERE"
    ]
    light_options = [
        u"%s IS THERE",
        u"YOU MIGHT SEE %s",
        u"LOOK TOWARDS %s"
    ]
    send_options = [
        u"SEND A SIGNAL NOW",
        u"LAUNCH A CRAFT TODAY",
        u"THINK TOWARDS %s",
        u"AVOID CALLING %s"
    ]
    recent_options = [
        u"IS YOUR PAST",
        u"CAN BE RECALLED"
    ]
    old_options = [
        u"IS OUR PAST",
        u"IS BEYOND OUR MEMORY"
    ]
    old_wait_options = [
        u"you can't wait",
        u"you won't wait",
        u"you must wait",
        u"you will wait",
        u"you will wait beyond your life"
    ]


    # If the sun is out...
    if planets_and_stars["Sun"]:
        sun_out = True
    else:
        sun_out = False

    print("Sun is out: %s" % sun_out)

    # For now, remove solar system bodies
    # TODO
    # Change this eventually
    names = planets_and_stars.keys()
    for body in solar_system_bodies:
        names.remove(body)
    shuffle(names)
    name = choice(names)
    ly = stars_expanded_distances[name]
    if (name == "Betelgeuse"): name = "Betel-geuse"

    every_moment.append(choice(opening_options))
   
    if sun_out:
        every_moment.append(choice(no_light_options) % name.upper())
    else:
        every_moment.append(choice(light_options) % name.upper())

    nearest_year = int(ly - (ly%10))
    if (nearest_year < 10):
        nearest_year = int(ly)

    every_moment.append(u"YOU FEEL NOW")
    every_moment.append(u"WHAT IS ABOUT %d YEARS OLD" % nearest_year)
    every_moment.append(u"THE TIME OF THIS LIGHT")
    if (nearest_year > YEAR_THRESHOLD):
        every_moment.append(choice(old_options))
    else:
        every_moment.append(choice(recent_options))

    #every_moment.append(u"IS YOUR PAST")

    if (nearest_year > YEAR_THRESHOLD):
        every_moment.append(u"what remains of this past")
        every_moment.append(u"what remains of this past")
    else:
        every_moment.append(u"what do you remember")
        every_moment.append(u"what do you remember")
        every_moment.append(u"what do you remember of the past %d years" % nearest_year)

    send = choice(send_options)
    if send.find("%") != -1:
        every_moment.append(send % name.upper())
    else:
        every_moment.append(send)

    if (nearest_year > YEAR_THRESHOLD):
        every_moment.append(choice(old_wait_options))
        every_moment.append(choice(old_wait_options))
        every_moment.append(choice(old_wait_options))
    else:
        every_moment.append(u"wait wait wait")
        every_moment.append(u"wait for %d years" % (nearest_year * 2))
        every_moment.append(u"(don't wait) (don't wait) (don't wait)")
        every_moment.append(u"(don't wait for %d years)" % (nearest_year * 2))

    every_moment.append(u"for a response")

    if (nearest_year > YEAR_THRESHOLD):
        every_moment.append(u"WHAT OF NOW")
        every_moment.append(u"WILL BE HERE THEN")
        every_moment.append(u"IN THIS PLACE")
        every_moment.append(u"IN THE PRESENT OF %s" % name.upper())
        pass
    else:
        every_moment.append(u"YOUR FUTURE WILL BE")
        every_moment.append(u"THE PRESENT OF %s" % name.upper())


    #every_moment.append("This is the name: %s" % name)
    #every_moment.append("This is how far away it is: %f" % ly)

    #every_moment[-1] = every_moment[-1].rstrip(",")
    #every_moment[-1] = u"%s." % every_moment[-1]

    if whole:
        everyMomentPoem = unicode("|".join(every_moment))
        poem = {"every_moment_title": u"Every moment again".encode("utf-8"), "every_moment_poem": everyMomentPoem.encode("utf-8")}
        poemSave = poem
        poemSave["qth"] = qth
        poemSave["time"] = time.time()
        filename = "every_moment_%d.json" % int(round(poemSave["time"]))
        with open(os.path.join("poems", filename), 'w') as f:
            f.write(json.dumps(poemSave))

        return poem
    else:
        encodedEveryMomentPoem = []
        for line in every_moment:
            encodedEveryMomentPoem.append(line.encode("utf-8"))
        return {"every_moment_title": u"Every moment again".encode("utf-8"), "every_moment_poem": encodedEveryMomentPoem}


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

def generateSatPoem(satInfo, qth = [], whole = True):
    """
(The earth | She) drags the (object type) back to the (surface | ground | crust)
(Remember | Forget | Recall | Understand) its name, "(sat name)"
(Hurled | Thrown | Launched) to the heavens upon fire (a while a go | a long time ago | recently)
It will be reduced to dust.
"""
    subjects = [u"The earth", u"The Field", u"He", u"She", u"Friction", u"The \u00E6ther"]
    actions = [u"drags", u"attracts", u"slows", u"decays"]
    surfaces = [u"surface", u"ground", u"crust", u"atmosphere", u"cloudtops"]
    remembers = [u"Remember", u"Forget", u"Recall", u"Understand", u"Know", u"Wonder about", u"Question"]
    hurleds = [u"Hurled", u"Thrown", u"Launched", u"Propelled", u"Thrust"]
    endings = [u"It will be reduced to dust.", u"It will remain aloft, forever.", u"It will be jostled by the solar wind.", u"It tumbles and tumbles, incessantly.", u"It will remain, still, in the cold void."]
    time_launched = timeAgo(satInfo["launch_year"])

    satPoemLines = []

    satPoemLines.append(u"EL %d DEGREES" % (int(round(float(satInfo["elevation"])))))
    satPoemLines.append(u"%s %s the %s above the %s" % (choice(subjects), choice(actions), satInfo["object_type"].lower(), choice(surfaces)))
    satPoemLines.append(u"%s its name, \u201C%s\u201D" % (choice(remembers), satInfo["satname"]))
    satPoemLines.append(u"%s to the heavens upon fire %s" % (choice(hurleds), time_launched))
    satPoemLines.append(choice(endings))

    """
    satPoem = "EL %d DEGREES\n\n" % (int(round(float(satInfo["elevation"]))))
    satPoem = "%s%s drags the %s back to the %s\n\n" % (satPoem, choice(subjects), satInfo["object_type"].lower(), choice(surfaces))
    satPoem = "%s%s its name, \"%s\"\n\n" % (satPoem, choice(remembers), satInfo["satname"])
    satPoem = "%s%s to the heavens upon fire %s\n\n" % (satPoem, choice(hurleds), time)
    satPoem = "%sIt will be reduced to dust." % (satPoem)
    """

    if whole:
        satPoem = unicode("\n\n".join(satPoemLines[1:]))
        print satPoem.encode("utf-8") 

        poemReturn = {"title": satPoemLines[0].encode("utf-8"), "poem": satPoem.encode("utf-8")}

        return poemReturn
    else:
        encodedSatPoem = []
        for line in satPoemLines[1:]:
            encodedSatPoem.append(line.encode("utf-8"))
        return {"title": satPoemLines[0].encode("utf-8"), "poem": encodedSatPoem}

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
api.add_resource(SatellitesAbovePoemOffset, "/sats/pebble/poem/<string:qth>/<string:offset>")
api.add_resource(PlanetsStarsAbove, "/planets_stars/pebble/<string:qth>")
api.add_resource(PlanetsStarsAbovePoems, "/planets_stars/pebble/poem/<string:qth>")
api.add_resource(PlanetsStarsEveryMoment, "/planets_stars_every_moment/pebble/<string:qth>")
api.add_resource(PlanetsStarsEveryMomentPoems, "/planets_stars_every_moment/pebble/poem/<string:qth>")


if __name__ == "__main__":
    #application.run(host="0.0.0.0")
    application.run(host="127.0.0.1",port=34567)
