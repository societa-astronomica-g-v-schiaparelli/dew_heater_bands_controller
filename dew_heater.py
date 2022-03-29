#!/usr/bin/env python3.10

# DEW HEATER
# Copyright (c) 2021-2022 Società Astronomica G.V. Schiaparelli
# Paolo Galli <paolo97gll@gmail.com>


import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from pytz import utc

import numpy as np
import skyfield.almanac
import skyfield.api
from aiohttp import ClientSession, web
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from RPi import GPIO


#####################################################################
# BASIC CONFIGURATION


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d %(levelname)s %(module)s - %(funcName)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
# set apscheduler executors logger on error and above
logging.getLogger('apscheduler.executors.default').setLevel(logging.ERROR)

SCRIPT_PATH = os.path.abspath(os.path.dirname(__file__))

# default to auto handle
AUTO_UPDATE = True

# dictionary {GPIO_pin: telescope_name}
RELAY = {2: "main", 3: "guide"}
# dictionary {GPIO_read: bool}
STATUS = {0: True, 1: False}
# aliases for ON and OFF
ON, OFF = GPIO.LOW, GPIO.HIGH

# setup GPIO
GPIO.setmode(GPIO.BCM)
for pin in RELAY:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, OFF)

# setup CDF location for Sun altitude
ts_skyfield = skyfield.api.load.timescale()
location_skyfield = skyfield.api.wgs84.latlon(45.86833333, 8.77055556)
sun_is_up = skyfield.almanac.sunrise_sunset(skyfield.api.load("de421.bsp"), location_skyfield)


#####################################################################
# get_meteo_data


async def get_meteo_data() -> tuple[float]:
    """ Function to get temperature and humidity at the telescope location."""
    async with ClientSession() as session:
        async with session.get("https://astrogeo.va.it/data/stazioni/cdf.json") as resp:
            meteo_data = await resp.json()
    # get temperature and humidity
    return float(meteo_data["tempcorr"]), float(meteo_data["rhcorr"])


#####################################################################
# Global functions


TEMPERATURE_THRESHOLD = 4
TIME_THRESHOLD = 30*60
DATETIME = datetime.now() - timedelta(seconds=TIME_THRESHOLD+1)

async def update_status():
    global DATETIME
    if AUTO_UPDATE:
        if sun_is_up(ts_skyfield.now()):
            logging.info("System disabled (daily hours)")
            for pin in RELAY:
                GPIO.output(pin, OFF)
        else:
            logging.info("Starting auto update routine")
            try:
                temperature, humidity = await get_meteo_data()
                # compute dewpoint
                a, m, Tn = 6.116441, 7.591386, 240.7263
                Pws = a * 10**(m * temperature / (temperature + Tn))
                Pw = Pws * humidity / 100
                dew_point = round(Tn / ((m / np.log10(Pw / a)) - 1), 1)
            except Exception as e:
                logging.exception(e)
                logging.info("System disabled (error retriving parameters)")
                for pin in RELAY:
                    GPIO.output(pin, OFF)
            else:
                logging.info(f"Temperature: {temperature} °C, Dew Point: {dew_point} °C")
                delta = temperature - dew_point
                if delta < TEMPERATURE_THRESHOLD:
                    logging.info("System enabled")
                    DATETIME = datetime.now()
                    for pin in RELAY:
                        GPIO.output(pin, ON)
                elif delta > TEMPERATURE_THRESHOLD and (datetime.now() - DATETIME).seconds > TIME_THRESHOLD:
                    logging.info("System disabled")
                    for pin in RELAY:
                        GPIO.output(pin, OFF)
                else:
                    logging.info("Waiting for disabling system")


#####################################################################
# WEBSERVER


async def start_webserver():

    routes = web.RouteTableDef()

    def get_language(request: web.Request):
        try:
            lang = request.headers["Accept-Language"].split(",")[0].split(";")[0].split("-")[0]
            return "it" if lang == "it" else "en"
        except Exception:
            return "en"

    @routes.get("/")
    async def _(request: web.Request):
        return web.FileResponse(f"{SCRIPT_PATH}/html/{get_language(request)}/index.html")

    @routes.get("/static/{file}")
    async def _(request: web.Request):
        lang_path = f"{SCRIPT_PATH}/html/{get_language(request)}/{request.match_info['file']}"
        common_path = f"{SCRIPT_PATH}/html/common/{request.match_info['file']}"
        return web.FileResponse(lang_path if os.path.exists(lang_path) else common_path)

    @routes.get("/api")
    async def _(request: web.Request):
        global AUTO_UPDATE
        params = request.rel_url.query
        headers = {"Access-Control-Allow-Origin": "*"}
        # check "json" param
        if "json" in params:
            # try parse and check syntax
            try:
                data = json.loads(params["json"])
                assert "cmd" in data
                assert data["cmd"] in ("set", "status")
                if data["cmd"] == "set":
                    assert "params" in data and data["params"]
                    assert set(data["params"]) <= {"auto", "telescope"}
                    if "auto" in data["params"]:
                        assert isinstance(data["params"]["auto"], bool)
                    if "telescope" in data["params"]:
                        assert set(data["params"]["telescope"]) <= set(RELAY.values())
                        for telescope in data["params"]["telescope"]:
                            assert isinstance(data["params"]["telescope"][telescope], bool)
                elif data["cmd"] == "status":
                    assert "params" not in data
            except Exception:
                return web.json_response({"rsp": "Error: wrong json format"}, status=400, headers=headers)
            # set
            if data["cmd"] == "set":
                if "auto" in data["params"]:
                    AUTO_UPDATE = data["params"]["auto"]
                    await update_status()
                if "telescope" in data["params"]:
                    if AUTO_UPDATE:
                        return web.json_response({"rsp": "Error: controller in automatic mode"}, headers=headers)
                    for pin, telescope in RELAY.items():
                        if telescope in data["params"]["telescope"]:
                            GPIO.output(pin, ON if data["params"]["telescope"][telescope] else OFF)
                return web.json_response({"rsp": "done"}, headers=headers)
            # status
            elif data["cmd"] == "status":
                data = {
                    "rsp": {
                        "auto": AUTO_UPDATE,
                        "telescope": {
                            telescope: STATUS[GPIO.input(pin)] for pin, telescope in RELAY.items()
                        }
                    }
                }
                return web.json_response(data, headers=headers)
            # command error
            else:
                return web.json_response({"rsp": "Error: unknown request"}, status=400, headers=headers)
        # param error
        else:
            return web.json_response({"rsp": "Error: unknown params"}, status=400, headers=headers)

    # setup application
    webserver = web.Application()
    webserver.add_routes(routes)

    # setup runner and start site
    runner = web.AppRunner(webserver)
    await runner.setup()
    site = web.TCPSite(runner, port=8001)
    await site.start()

    # sleep forever
    while True:
        await asyncio.sleep(3600)


#####################################################################
# SCHEDULER


async def start_scheduler():

    scheduler = AsyncIOScheduler(timezone=utc)

    # add update job
    scheduler.add_job(update_status, "cron", minute="5,15,25,35,45,55", next_run_time=datetime.now())

    # start scheduler
    scheduler.start()

    # sleep forever
    while True:
        await asyncio.sleep(3600)


#####################################################################


async def main():
    await asyncio.gather(start_webserver(), start_scheduler())

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Interrupt detected, exit")
    # clean GPIO
    GPIO.cleanup()
