#!/usr/bin/env python
import cPickle, os, time

import memcache

from spacetrack import SpaceTrackClient

from st_credentials import stUsername, stPassword

sat_files = ["science-sats.txt", "visual-sats.txt", "geo-sats.txt", "resource-sats.txt", "stations-sats.txt", "weather-sats.txt"]

class TLEUpdate(object):
    """Class for updating TLEs and saving to memcached and pickle files"""

    def __init__(self, satFilename, stUsername, stPassword, pickleSave = False, dataDir = "./"):
        self.satFilename = satFilename
        self.stUsername = stUsername
        self.stPassword = stPassword
        self.pickleSave = pickleSave

        # Get base name from the satellite filename
        self.satType = os.path.splitext(self.satFilename)[0]

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

                self.mc.set("%s-info" % id, satInfoDict)
                satInfos.append(satInfoDict)

            # If we're to update the pickle file, do so
            if self.pickleSave:
                with open("%s.pickle" % self.satType, "wb") as f:
                    cPickle.dump(satInfos, f)

    def getIDs(self):
        # TODO: Error handling

        ids = self.mc.get("%s-ids" % self.satType)

        if ids is None:
            # Need to get the IDs and put them in memcached
            with open(self.satFilename, "r") as f:
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
