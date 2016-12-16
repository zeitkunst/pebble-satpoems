#!/usr/bin/env python
import cPickle, os, time

import memcache

import predict
from spacetrack import SpaceTrackClient
import ephem

from st_credentials import stUsername, stPassword, homeQTH

sat_files = ["science-sats.txt", "visual-sats.txt", "geo-sats.txt", "resource-sats.txt", "stations-sats.txt", "weather-sats.txt"]

sat_types = {
    "science-sats": {"filename": "science-sats.txt"}, 
    "visual-sats": {"filename": "visual-sats.txt"}, 
    "geo-sats": {"filename": "geo-sats.txt"}, 
    "resource-sats": {"filename": "resource-sats.txt"}, 
    "stations-sats": {"filename": "stations-sats.txt"}, 
    "weather-sats": {"filename": "weather-sats.txt"}
}

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


class SatInfo(object):
    def __init__(self, qth = homeQTH, satType = "visual-sats"):
        self.satType = satType
        self.qth = qth

        self.mc = memcache.Client(['127.0.0.1:11211'], debug = 0)

    def getIDs(self):
        # TODO: Error handling

        ids = self.mc.get("%s-ids" % self.satType)

        if ids is None:
            # Then we probably need to update things
            update = SatInfoUpdate(sat_types[self.satType]["filename"])
            update.updateSatInfo()
        else:
            return ids

    def getSatellitesAbove(self):
        sats = {}

        ids = self.getIDs()
    
        for id in ids:
            data = self.mc.get("%s-data" % id)
            tle = "%s\n%s\n%s" % (data["satcat"]["SATNAME"], data["tle"][0], data["tle"][1])
            p = predict.observe(tle, self.qth)
        
            # This just gets me things above the horizon, not things actually visible
            if p["elevation"] > 0:
                #print "%s\nObject Type: %s\nNORAD ID: %s\nElevation: %s\nVisible: %s\n" % (p["name"],satData[ID]["catalogInfo"][0]["OBJECT_TYPE"], ID, p["elevation"], p["visibility"])
                resultData = data
                resultData["prediction"] = p
                sats[id] = resultData
    
        return sats

    def parseSatellitesAboveResults(self, sats):
        # Create our json result
        result = {}
        for key in sats.keys():
            result[key] = {
                "elevation": sats[key]["prediction"]["elevation"],
                "visibility": sats[key]["prediction"]["visibility"],
                "geostationary": sats[key]["prediction"]["geostationary"],
                "satname": sats[key]["satcat"]["SATNAME"],
                "object_type": sats[key]["satcat"]["OBJECT_TYPE"],
                "country": sats[key]["satcat"]["COUNTRY"],
                "launch_year": sats[key]["satcat"]["LAUNCH_YEAR"],
                "launch": sats[key]["satcat"]["LAUNCH"]
    
            }
    
        return result

class SatInfoUpdate(object):
    """Class for updating TLEs and saving to memcached and pickle files"""

    def __init__(self, satFilename, stUsername = stUsername, stPassword = stPassword, pickleSave = False, dataDir = "data"):
        self.dataDir = dataDir
        self.satFilename = os.path.join(self.dataDir, satFilename)
        self.stUsername = stUsername
        self.stPassword = stPassword
        self.pickleSave = pickleSave

        # Get base name from the satellite filename
        self.satType = os.path.splitext(satFilename)[0]

        self.st = SpaceTrackClient(self.stUsername, self.stPassword)

        self.mc = memcache.Client(['127.0.0.1:11211'], debug = 0)

    def updateSatInfo(self, force = False):
        """ Update the TLEs, possibly with pickled file as well"""

        self.ids = self.getIDs()

        timestamp = self.mc.get("%s-timestamp" % self.satType)

        if timestamp is None: timestamp = 0

        # If it's been longer than a day, update sat info
        if (((time.time() - timestamp) > 86400) or force):
            self.tles = self.getTLEs(self.ids)
            self.satcats = self.getSATCATs(self.ids)
    
            self.mc.set("%s-ids" % self.satType, self.ids)
            self.mc.set("%s-timestamp" % self.satType, time.time())
   
            satInfos = []
            for id in self.ids:
                satInfoDict = {}
                satInfoDict["tle"] = self.tles[id]
                satInfoDict["satcat"] = self.satcats[id]

                self.mc.set("%s-data" % id, satInfoDict)
                satInfos.append(satInfoDict)

            # If we're to update the pickle file, do so
            if self.pickleSave:
                with open(os.path.join(self.dataDir, "%s.pickle" % self.satType), "wb") as f:
                    cPickle.dump(satInfos, f)

    def getIDs(self):
        # TODO: Error handling

        ids = self.mc.get("%s-ids" % self.satType)

        if ids is None:
            # Need to get the IDs and put them in memcached
            with open(os.path.join(self.satFilename), "r") as f:
                data = f.readlines()
        
            ids = []
            for item in data:
                id = item.split("\t")[1].strip()
                ids.append(id.lstrip("0"))
        
            self.ids = ids
            self.mc.set("%s-ids" % self.satType, self.ids)

            return ids
        else:
            self.ids = ids
            return ids

    def getSATCATs(self, ids):
        """Get an updated version of SATCATs based on a list of NORAD IDs"""
        # TODO: Error handling

        # Get the SATCATs for the given list of IDs
        satcats = self.st.satcat(norad_cat_id = ids)

        # Create a dictionary where the keys are IDs and the values are the satcats
        satcatDictionary = {}
        for item in xrange(0, len(ids)):
            satcatDictionary[ids[item]] = satcats[item]

        return satcatDictionary

    def getTLEs(self, ids):
        """Get an updated version of TLEs based on a list of NORAD IDs"""
        # TODO: Error handling

        # Get the TLEs for the given list of IDs
        tles = self.st.tle_latest(norad_cat_id=ids, ordinal=1, format='tle')

        # Split out the TLEs and remove an extraneous element
        tles = tles.split("\n")
        tles.pop()

        # Create a dictionary where the keys are IDs and the values are the TLEs, as a two element list
        tleDictionary = {}
        for item in xrange(0, len(ids)):
            tleDictionary[ids[item]] = (tles[item*2], tles[item*2 + 1])

        return tleDictionary
