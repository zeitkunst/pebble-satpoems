#!/usr/bin/env python

# For now...
import cPickle

import predict
from spacetrack import SpaceTrackClient

from flask import Flask, request
from flask_restful import Resource, Api
from json import dumps

application = Flask(__name__)
api = Api(application)

homeQTH = (42.294615, 71.302342, 185)

with open("satelliteData.pickle", "rb") as f:
    satData = cPickle.load(f)

class SatellitesAbove(Resource):
    def get(self, qth):
        qthSplit = qth.split(",")
        
        if (len(qthSplit) == 2):
            # Assume 1000ft for elevation if non given
            sats = getSatellitesAbove((qthSplit[0], qthSplit[1], 1000))
        else:
            sats = getSatellitesAbove((qthSplit[0], qthSplit[1], qthSplit[2]))

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
    #sats = getSatellitesAbove(homeQTH)
    #print sats
    application.run(host="0.0.0.0")
