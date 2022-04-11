#!/usr/bin/env python3.10

# DEW HEATER
# Copyright (c) 2021-2022 Società Astronomica G.V. Schiaparelli
# Paolo Galli <paolo97gll@gmail.com>


import asyncio
import logging
import os
from datetime import datetime, timedelta

import numpy as np
import skyfield.almanac
import skyfield.api
import ujson
from aiohttp import ClientSession, web
from gpiozero import DigitalOutputDevice


#####################################################################
# BASIC CONFIGURATION


logging_format = "[%(asctime)s] (%(levelname)s) %(module)s - %(funcName)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=logging_format)

class ColoredFormatter(logging.Formatter):
    bold_blue = "\x1b[34;1m"
    grey = "\x1b[37;20m"
    green = "\x1b[32;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    DEFAUTL_FORMATTER = logging.Formatter(logging_format)
    FORMATTERS = {
        1: logging.Formatter(bold_blue + logging_format + reset),
        logging.DEBUG: logging.Formatter(grey + logging_format + reset),
        logging.INFO: logging.Formatter(green + logging_format + reset),
        logging.WARNING: logging.Formatter(yellow + logging_format + reset),
        logging.ERROR: logging.Formatter(red + logging_format + reset),
        logging.CRITICAL: logging.Formatter(bold_red + logging_format + reset)
    }
    def format(self, record: logging.LogRecord) -> str:
        return self.FORMATTERS.get(record.levelno, self.DEFAUTL_FORMATTER).format(record)

(logger := logging.getLogger(__name__)).setLevel(1)
logger.propagate = False
(logger_handler := logging.StreamHandler()).setFormatter(ColoredFormatter())
logger.addHandler(logger_handler)

SCRIPT_PATH = os.path.abspath(os.path.dirname(__file__))

# default to auto handle
AUTO_UPDATE = True

RELAY = {
    "main":  DigitalOutputDevice(pin="GPIO2", active_high=False),
    "guide": DigitalOutputDevice(pin="GPIO3", active_high=False)
}

# setup CDF location for Sun altitude
ts_skyfield = skyfield.api.load.timescale()
location_skyfield = skyfield.api.wgs84.latlon(45.86833333, 8.77055556)
sun_is_up = skyfield.almanac.sunrise_sunset(skyfield.api.load("de421.bsp"), location_skyfield)


#####################################################################
# get_meteo_data


async def get_meteo_data() -> tuple[float]:
    """ Function to get temperature and humidity at the telescope location. """
    async with ClientSession() as session:
        async with session.get("https://astrogeo.va.it/data/stazioni/cdf.json") as resp:
            meteo_data = await resp.json(loads=ujson.loads)
    # get temperature and humidity
    return float(meteo_data["tempcorr"]), float(meteo_data["rhcorr"])


#####################################################################
# Global functions


TEMPERATURE_THRESHOLD = 4
TIME_THRESHOLD = 30*60
DATETIME = datetime.now() - timedelta(seconds=TIME_THRESHOLD+1)
UPDATER_LOCK = asyncio.Lock()

async def update_status() -> None:
    global DATETIME
    if AUTO_UPDATE:
        async with UPDATER_LOCK:
            if sun_is_up(ts_skyfield.now()):
                logger.info("System disabled (daily hours)")
                for relay in RELAY.values():
                    relay.off()
            else:
                logger.info("Starting auto update routine")
                try:
                    temperature, humidity = await get_meteo_data()
                    # compute dewpoint
                    a, m, Tn = 6.116441, 7.591386, 240.7263
                    Pws = a * 10**(m * temperature / (temperature + Tn))
                    Pw = Pws * humidity / 100
                    dew_point = round(Tn / ((m / np.log10(Pw / a)) - 1), 1)
                except Exception as e:
                    logger.exception(e)
                    logger.info("System disabled (error retriving parameters)")
                    for relay in RELAY.values():
                        relay.off()
                else:
                    logger.info(f"Temperature: {temperature} °C, Dew Point: {dew_point} °C")
                    delta = temperature - dew_point
                    if delta < TEMPERATURE_THRESHOLD:
                        logger.info("System enabled")
                        DATETIME = datetime.now()
                        for relay in RELAY.values():
                            relay.on()
                    elif delta > TEMPERATURE_THRESHOLD and (datetime.now() - DATETIME).seconds > TIME_THRESHOLD:
                        logger.info("System disabled")
                        for relay in RELAY.values():
                            relay.off()
                    else:
                        logger.info("Waiting for disabling system")


#####################################################################
# WEBSERVER


async def task_webserver() -> None:

    routes = web.RouteTableDef()

    def get_language(request: web.Request) -> str:
        try:
            lang = request.headers["Accept-Language"].split(",")[0].split(";")[0].split("-")[0]
            return "it" if lang == "it" else "en"
        except Exception:
            return "en"

    @routes.get("/")
    async def webserver_route_root(request: web.Request):
        return web.FileResponse(f"{SCRIPT_PATH}/html/{get_language(request)}/index.html")

    @routes.get("/static/{file}")
    async def webserver_route_static(request: web.Request):
        lang_path = f"{SCRIPT_PATH}/html/{get_language(request)}/{request.match_info['file']}"
        common_path = f"{SCRIPT_PATH}/html/common/{request.match_info['file']}"
        return web.FileResponse(lang_path if os.path.exists(lang_path) else common_path)

    @routes.get("/api")
    async def webserver_route_api(request: web.Request):
        global AUTO_UPDATE
        params = request.rel_url.query
        headers = {"Access-Control-Allow-Origin": "*"}
        # check "json" param
        if "json" in params:
            # try parse and check syntax
            try:
                data = ujson.loads(params["json"])
                assert "cmd" in data
                assert data["cmd"] in ("set", "status")
                if data["cmd"] == "set":
                    assert "params" in data and data["params"]
                    assert set(data["params"]) <= {"auto", "telescope"}
                    if "auto" in data["params"]:
                        assert isinstance(data["params"]["auto"], bool)
                    if "telescope" in data["params"]:
                        assert set(data["params"]["telescope"]) <= set(RELAY)
                        for telescope in data["params"]["telescope"]:
                            assert isinstance(data["params"]["telescope"][telescope], bool)
                elif data["cmd"] == "status":
                    assert "params" not in data
            except Exception:
                return web.json_response({"rsp": "Error: wrong json format"}, status=400, headers=headers, dumps=ujson.dumps)
            # set
            if data["cmd"] == "set":
                if "auto" in data["params"]:
                    AUTO_UPDATE = data["params"]["auto"]
                    logger.info(f"Auto update {'enabled' if AUTO_UPDATE else 'disabled'}")
                    await update_status()
                if "telescope" in data["params"]:
                    if AUTO_UPDATE:
                        logger.error("Controller in automatic mode, enable manual mode first")
                        return web.json_response({"rsp": "Error: controller in automatic mode, enable manual mode first"}, headers=headers, dumps=ujson.dumps)
                    for telescope, relay in RELAY.items():
                        if telescope in data["params"]["telescope"]:
                            logger.info(f"{telescope.capitalize()} {'enabled' if data['params']['telescope'][telescope] else 'disabled'}")
                            (relay.on if data["params"]["telescope"][telescope] else relay.off)()
                return web.json_response({"rsp": "done"}, headers=headers, dumps=ujson.dumps)
            # status
            elif data["cmd"] == "status":
                data = {
                    "rsp": {
                        "auto": AUTO_UPDATE,
                        "telescope": {
                            telescope: relay.is_active for telescope, relay in RELAY.items()
                        }
                    }
                }
                return web.json_response(data, headers=headers, dumps=ujson.dumps)
            # command error
            else:
                return web.json_response({"rsp": "Error: unknown request"}, status=400, headers=headers, dumps=ujson.dumps)
        # param error
        else:
            return web.json_response({"rsp": "Error: unknown params"}, status=400, headers=headers, dumps=ujson.dumps)

    # setup application
    webserver = web.Application()
    webserver.add_routes(routes)

    # setup runner and start site
    runner = web.AppRunner(webserver)
    await runner.setup()
    site = web.TCPSite(runner, port=8001)
    await site.start()
    logger.info("Webserver started!")

    # sleep forever
    while True:
        await asyncio.sleep(3600)


#####################################################################
# UPDATER (get meteo data and update dew heater)


async def task_updater() -> None:
    logger.info("Updater task started!")
    while True:
        await update_status()
        await asyncio.sleep(300)
    # wrong exit
    logger.critical("Unexpected task exit, aborting")
    exit(1)


#####################################################################


async def main():
    await asyncio.gather(task_webserver(), task_updater())

if __name__ == "__main__":
    try:
        logger.log(1, "[MAIN] Starting app: dew_heater")
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.log(1, "[MAIN] Interrupt detected, exit")
